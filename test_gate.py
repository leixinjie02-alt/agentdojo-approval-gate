"""Tests for Member 1. Run:  python -m pytest test_gate.py -v   (no API key needed)"""
import itertools, json, statistics
import pytest
from agentdojo.agent_pipeline import AgentPipeline, BasePipelineElement, InitQuery, SystemMessage, ToolsExecutionLoop
from agentdojo.functions_runtime import EmptyEnv, FunctionsRuntime
from agentdojo.task_suite import get_suite
from agentdojo.types import ChatAssistantMessage, text_content_block_from_string
from approval_gate import *


class ScriptedLLM(BasePipelineElement):
    """Fake agent: replays a fixed list of tool calls, one per turn. Costs nothing."""
    def __init__(self, calls): self.calls, self.i = calls, 0
    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        tc = [self.calls[self.i]] if self.i < len(self.calls) else None
        self.i += 1
        msg = ChatAssistantMessage(role="assistant", content=[text_content_block_from_string("ok")], tool_calls=tc)
        return query, runtime, env, [*messages, msg], extra_args


class SeqPolicy:
    def __init__(self, seq): self.seq = iter(seq)
    def decide(self, ctx): return next(self.seq)

class SeqReviewer:
    def __init__(self, seq): self.seq, self.n = iter(seq), 0
    def review(self, ctx): self.n += 1; return next(self.seq)


def run(policy, reviewer, k, n_calls=None, log=None):
    suite = get_suite("v1.2", "banking")
    task = suite.user_tasks["user_task_1"]
    env = suite.load_and_inject_default_environment({})
    calls = task.ground_truth(env)
    calls = list(itertools.islice(itertools.cycle(calls), n_calls or len(calls)))
    gate = ApprovalGate(policy, reviewer, k, log_path=log)
    llm = ScriptedLLM(calls)
    pipe = AgentPipeline([BudgetReset(gate), SystemMessage("sys"), InitQuery(), llm, ToolsExecutionLoop([gate, llm])])
    _, _, _, msgs, _ = pipe.query(task.PROMPT, FunctionsRuntime(suite.tools), env)
    return gate, msgs


A, D, E = Decision.APPROVE, Decision.DENY, Decision.ESCALATE

def reference(decisions, reviews, k):
    """Independent, obviously-correct spec of the budget state machine."""
    rem, rv, out = k, iter(reviews), []
    for d in decisions:
        if d is A: out.append(("auto_approved", rem, rem))
        elif d is D: out.append(("auto_denied", rem, rem))
        elif rem == 0: out.append(("budget_exhausted_denied", 0, 0))
        else:
            out.append(("human_approved" if next(rv) else "human_denied", rem, rem - 1)); rem -= 1
    return out


@pytest.mark.parametrize("k", [0, 1, 2, 3])
def test_state_machine_exhaustive(k):
    """All 3^n decision sequences x all reviewer answers, for n = 4 tool calls."""
    n = 4
    for decisions in itertools.product([A, D, E], repeat=n):
        for reviews in itertools.product([True, False], repeat=min(k, decisions.count(E))):
            pad = list(reviews) + [True] * n
            reviewer = SeqReviewer(pad)
            gate, _ = run(SeqPolicy(decisions), reviewer, k, n_calls=n)
            got = [(r.outcome, r.budget_before, r.budget_after) for r in gate.records]
            assert got == reference(decisions, pad, k)
            assert reviewer.n == min(k, decisions.count(E))           # reviewer never called beyond k
            assert all(r.executed == (r.outcome in ("auto_approved", "human_approved")) for r in gate.records)
            assert 0 <= gate.budget.remaining <= k


def test_denied_call_is_not_executed():
    gate, msgs = run(SeqPolicy([D] * 9), AlwaysApproveReviewer(), k=5)
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert tool_msgs and all(m["error"] == ApprovalGate.DENY_MSG for m in tool_msgs)

def test_full_approve_matches_unguarded():
    gate, msgs = run(FullApprovePolicy(), AlwaysApproveReviewer(), k=0)
    assert all(r.outcome == "auto_approved" for r in gate.records)
    assert all(m["error"] is None for m in msgs if m["role"] == "tool")

def test_budget_resets_between_tasks():
    gate, _ = run(FullEscalatePolicy(), AlwaysApproveReviewer(), k=1, n_calls=3)
    assert gate.budget.remaining == 0
    gate.start_task()
    assert gate.budget.remaining == 1 and gate.records == []

def test_log_file(tmp_path):
    p = tmp_path / "gate.jsonl"
    run(FullEscalatePolicy(), AlwaysApproveReviewer(), k=1, n_calls=3, log=p)
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    assert [r["outcome"] for r in rows] == ["human_approved", "budget_exhausted_denied", "budget_exhausted_denied"]

def test_gate_overhead_latency():
    xs = []
    for _ in range(200):
        gate, _ = run(FullEscalatePolicy(), AlwaysApproveReviewer(), k=2, n_calls=4)
        xs += [r.gate_overhead_ms for r in gate.records]
    xs.sort()
    print(f"\ngate overhead over {len(xs)} calls: mean={statistics.mean(xs):.3f}ms "
          f"p50={xs[len(xs)//2]:.3f}ms p95={xs[int(len(xs)*.95)]:.3f}ms max={xs[-1]:.3f}ms")
    assert xs[int(len(xs) * .95)] < 5
