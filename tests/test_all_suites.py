"""Stronger checks over ALL AgentDojo suites (no API key needed).
Run:  python -m pytest test_all_suites.py -v -s
"""
import datetime
import re

import pytest
from agentdojo.agent_pipeline import AgentPipeline, InitQuery, SystemMessage, ToolsExecutionLoop, ToolsExecutor
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite import get_suite
from approval_gate import (AlwaysApproveReviewer, ApprovalGate, BudgetReset, Decision,
                           FullApprovePolicy, FullEscalatePolicy)
from test_gate import ScriptedLLM

SUITES = ["banking", "slack", "travel", "workspace"]


def run(suite, task, executor, gate=None):
    env = suite.load_and_inject_default_environment({})
    pre = env.model_copy(deep=True)
    llm = ScriptedLLM(task.ground_truth(env))
    head = [BudgetReset(gate)] if gate else []
    pipe = AgentPipeline([*head, SystemMessage("sys"), InitQuery(), llm, ToolsExecutionLoop([executor, llm], max_iters=50)])
    _, _, env, msgs, _ = pipe.query(task.PROMPT, FunctionsRuntime(suite.tools), env)
    return pre, env, msgs


def snap(env):
    """Environment as a dict, masking wall-clock datetimes (AgentDojo stamps sent emails
    and edited files with datetime.now(), so two runs of the ORIGINAL executor already differ there)."""
    def walk(x):
        if isinstance(x, dict): return {k: walk(v) for k, v in x.items()}
        if isinstance(x, datetime.datetime) and x.microsecond: return "<now>"
        if isinstance(x, list): return [walk(v) for v in x]
        return x
    return walk(env.model_dump())


NOW = re.compile(r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d\.\d+")   # wall-clock stamps (have microseconds)


def strip(msgs):
    return [(m["role"], NOW.sub("<now>", str(m.get("content"))), m.get("error")) for m in msgs]


class DenyAll:
    def decide(self, ctx): return Decision.DENY


@pytest.mark.parametrize("name", SUITES)
def test_gate_is_transparent_and_blocks(name):
    suite = get_suite("v1.2", name)
    n_tasks = n_calls = 0
    for task in suite.user_tasks.values():
        # (a) full-approve gate == original AgentDojo executor: same messages, same final environment
        _, env0, msgs0 = run(suite, task, ToolsExecutor())
        g = ApprovalGate(FullApprovePolicy(), AlwaysApproveReviewer(), k=0)
        _, env1, msgs1 = run(suite, task, g, g)
        assert strip(msgs0) == strip(msgs1), task.ID
        assert snap(env0) == snap(env1), task.ID
        calls = len(g.records)

        # (b) full-escalate with k >= #calls behaves the same; budget spent == #calls
        g = ApprovalGate(FullEscalatePolicy(), AlwaysApproveReviewer(), k=calls)
        _, env2, msgs2 = run(suite, task, g, g)
        assert snap(env2) == snap(env0) and g.budget.remaining == 0, task.ID

        # (c) full-escalate with k = 0: nothing may execute, environment untouched
        g = ApprovalGate(FullEscalatePolicy(), AlwaysApproveReviewer(), k=0)
        pre, env3, _ = run(suite, task, g, g)
        assert snap(env3) == snap(pre) and all(r.outcome == "budget_exhausted_denied" for r in g.records), task.ID

        # (d) deny-all: nothing executes, environment untouched, every call intercepted
        g = ApprovalGate(DenyAll(), AlwaysApproveReviewer(), k=5)
        pre, env4, _ = run(suite, task, g, g)
        assert snap(env4) == snap(pre) and len(g.records) == calls and not any(r.executed for r in g.records), task.ID
        n_tasks += 1; n_calls += calls
    print(f"\n{name}: {n_tasks} tasks, {n_calls} tool calls checked")
