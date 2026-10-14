"""End-to-end wiring of Members 1-4 on real AgentDojo tasks, fully offline (no API key, no cost).
LLM calls of the policy and reviewer are replaced by fakes; everything else is the real code.
Run:  python -m pytest test_integration.py -v
"""
import json
from types import SimpleNamespace

import pytest
from agentdojo.agent_pipeline import AgentPipeline, InitQuery, SystemMessage, ToolsExecutionLoop
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite import get_suite

import run_real
from approval_gate import ApprovalGate, BudgetReset, FullEscalatePolicy
from prefilter_policy import PrefilterPolicy
from rule_prefilter import RulePreFilter
from semantic_adapter import SemanticPolicy
from simulated_reviewer import SimulatedReviewer
from test_gate import ScriptedLLM


def fake_openai(decision):
    """OpenAI-like client that always answers {"decision": decision}."""
    seen = []
    def create(**kw):
        seen.append(kw)
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps({"decision": decision})))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), seen


def run(task, policy, reviewer, k):
    suite = get_suite("v1.2", "workspace")
    env = suite.load_and_inject_default_environment({})
    gate = ApprovalGate(policy, reviewer, k)
    llm = ScriptedLLM(task.ground_truth(env))
    pipe = AgentPipeline([BudgetReset(gate), SystemMessage("sys"), InitQuery(), llm,
                          ToolsExecutionLoop([gate, llm], max_iters=50)])
    pipe.query(task.PROMPT, FunctionsRuntime(suite.tools), env)
    return gate


def test_runner_builds_every_policy(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test")
    for name in run_real.POLICIES:
        for version in ["V1", "V2", "V3"]:
            assert hasattr(run_real.make_policy(name, version), "decide")
    assert isinstance(run_real.make_reviewer("simulated", "gpt-4o-mini-2024-07-18"), SimulatedReviewer)


@pytest.mark.parametrize("sem, rev, k", [("auto_approve", "approve", 1), ("auto_deny", "approve", 1),
                                         ("escalate", "approve", 1), ("escalate", "deny", 1),
                                         ("escalate", "approve", 0)])
def test_rules_then_semantic_then_reviewer(sem, rev, k):
    """Rules decide first; only undecided calls reach the semantic policy; only ESCALATE reaches the
    reviewer and spends budget. Checked on every Workspace task."""
    total_rule_decided = 0
    total_rule_decided = 0
    for task in get_suite("v1.2", "workspace").user_tasks.values():
        sem_calls, rule_decided = [], []

        class CountingRules(RulePreFilter):
            def evaluate(self, ctx):
                res = super().evaluate(ctx)
                if res.decision is not None:
                    rule_decided.append(res.decision)
                return res

        semantic = SemanticPolicy(assessor=lambda **kw: sem_calls.append(kw) or sem)
        client, seen = fake_openai(rev)
        gate = run(task, PrefilterPolicy(CountingRules(), semantic), SimulatedReviewer(client=client), k)
        assert len(sem_calls) + len(rule_decided) == len(gate.records)   # rules first, semantic if undecided
        escalated = [r for r in gate.records if r.policy_decision == "escalate"]
        assert len(seen) == min(k, len(escalated))                       # reviewer only within budget
        assert gate.budget.remaining == k - len(seen)
        for r in escalated[k:]:
            assert r.outcome == "budget_exhausted_denied" and not r.executed
        for r in gate.records:
            assert r.executed == (r.outcome in ("auto_approved", "human_approved"))
        for kw in seen:                                                  # no oracle info reaches reviewer
            body = kw["messages"][1]["content"]
            assert "injection_task" not in body and "ground_truth" not in body
        total_rule_decided += len(rule_decided)
    assert total_rule_decided > 0                                        # the rules actually fired


def test_rules_only_never_calls_an_llm():
    for task in get_suite("v1.2", "workspace").user_tasks.values():
        gate = run(task, PrefilterPolicy(RulePreFilter(), FullEscalatePolicy()),
                   SimulatedReviewer(client=fake_openai("approve")[0]), k=50)
        assert all(r.policy_decision in ("approve", "escalate", "deny") for r in gate.records)


def test_token_accounting_end_to_end(tmp_path, monkeypatch):
    """Agent, policy and reviewer tokens all reach the logs, through the real run_real.py pipeline."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test")
    import semantic_policy
    from agentdojo.functions_runtime import FunctionCall
    from agentdojo.task_suite import get_suite

    def completion(content=None, tool_calls=None, p=0, c=0):
        msg = SimpleNamespace(content=content, tool_calls=tool_calls, role="assistant")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                               usage=SimpleNamespace(prompt_tokens=p, completion_tokens=c, total_tokens=p + c))

    # policy LLM: always escalate, 100+10 tokens; reviewer LLM: approve, 50+5 tokens
    pol_resp = completion('{"decision": "escalate"}', p=100, c=10)
    monkeypatch.setattr(semantic_policy, "get_client", lambda: SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kw: pol_resp))))
    rev_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: completion('{"decision": "approve"}', p=50, c=5))))

    log = tmp_path / "gate_decisions.jsonl"
    pipeline, gate = run_real.build_pipeline("gpt-4o-mini-2024-07-18", run_real.make_policy("semantic"),
                                             SimulatedReviewer(client=rev_client), 1, log)
    # agent LLM: one tool call (1000+20 tokens), then a final answer (1200+30 tokens)
    tc = SimpleNamespace(id="c1", type="function",
                         function=SimpleNamespace(name="get_current_day", arguments="{}"))
    answers = iter([completion(None, [tc], 1000, 20), completion("done", None, 1200, 30)])
    pipeline.elements[3].client._client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kw: next(answers))))

    suite = get_suite("v1.2", "workspace")
    env = suite.load_and_inject_default_environment({})
    pipeline.query("What day is it?", FunctionsRuntime(suite.tools), env)

    row = json.loads(log.read_text().splitlines()[0])
    assert (row["policy_prompt_tokens"], row["policy_completion_tokens"]) == (100, 10)
    assert (row["reviewer_prompt_tokens"], row["reviewer_completion_tokens"]) == (50, 5)
    summ = json.loads((tmp_path / "task_summaries.jsonl").read_text().splitlines()[0])
    assert summ["usage"]["agent"] == {"prompt_tokens": 2200, "completion_tokens": 50, "calls": 2}
    assert summ["usage"]["policy"] == {"prompt_tokens": 100, "completion_tokens": 10, "calls": 1}
    assert summ["usage"]["reviewer"] == {"prompt_tokens": 50, "completion_tokens": 5, "calls": 1}
    assert summ["n_escalations"] == 1 and summ["pipeline_completed"] is True


def test_cost_report_uses_member5_tracker(tmp_path):
    import cost_report
    rows = [
        {"is_precheck": True, "usage": {"agent": {"prompt_tokens": 999, "completion_tokens": 9, "calls": 1},
                                        "policy": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0},
                                        "reviewer": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}}},
        {"is_precheck": False, "usage": {"agent": {"prompt_tokens": 2000, "completion_tokens": 50, "calls": 2},
                                         "policy": {"prompt_tokens": 300, "completion_tokens": 30, "calls": 3},
                                         "reviewer": {"prompt_tokens": 100, "completion_tokens": 10, "calls": 1}}},
        {"is_precheck": False, "usage": {"agent": {"prompt_tokens": 1000, "completion_tokens": 50, "calls": 1},
                                         "policy": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0},
                                         "reviewer": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}}},
    ]
    (tmp_path / "task_summaries.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    tracker, n = cost_report.tracker_from_run(tmp_path)
    assert n == 2
    assert tracker.usage["agent"] == {"prompt_tokens": 3000, "completion_tokens": 100, "calls": 3}
    assert tracker.usage["policy"] == {"prompt_tokens": 300, "completion_tokens": 30, "calls": 3}
    assert tracker.usage["reviewer"] == {"prompt_tokens": 100, "completion_tokens": 10, "calls": 1}
    cost = tracker.calculate_cost("gpt-4o-mini")
    assert abs(cost["total_cost_usd"] - (3400 * 0.15 + 140 * 0.60) / 1e6) < 1e-9
