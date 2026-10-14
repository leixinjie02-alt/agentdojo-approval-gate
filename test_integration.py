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
