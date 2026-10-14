import pytest

from agentdojo.agent_pipeline import (
    AgentPipeline,
    InitQuery,
    SystemMessage,
    ToolsExecutionLoop,
)
from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime
from agentdojo.task_suite import get_suite

from approval_gate import ApprovalGate, BudgetReset, Decision
from prefilter_policy import PrefilterPolicy
from rule_prefilter import RulePreFilter
from test_gate import ScriptedLLM, SeqReviewer


class CountingEscalatePolicy:
    """A test-only downstream policy that always requests review."""

    def __init__(self):
        self.calls = 0

    def decide(self, ctx):
        self.calls += 1
        return Decision.ESCALATE


@pytest.mark.parametrize("reviewer_approved", [True, False])
def test_prefilter_gate_routing_and_budget(reviewer_approved):
    suite = get_suite("v1.2", "workspace")
    env = suite.load_and_inject_default_environment({})
    initial_state = env.model_dump()
    file_id = next(iter(env.cloud_drive.files))

    # Replay four tool calls without invoking a real language model.
    calls = [
        FunctionCall(
            function="get_current_day", args={}, id="call_1"
        ),
        FunctionCall(
            function="delete_file",
            args={"file_id": file_id},
            id="call_2",
        ),
        FunctionCall(
            function="get_file_by_id",
            args={"file_id": file_id},
            id="call_3",
        ),
        FunctionCall(
            function="get_file_by_id",
            args={"file_id": file_id},
            id="call_4",
        ),
    ]

    downstream = CountingEscalatePolicy()
    policy = PrefilterPolicy(
        prefilter=RulePreFilter(blocked_tools={"delete_file"}),
        downstream_policy=downstream,
    )
    reviewer = SeqReviewer([reviewer_approved])
    gate = ApprovalGate(policy, reviewer, k=1)
    agent = ScriptedLLM(calls)

    pipeline = AgentPipeline([
        BudgetReset(gate),
        SystemMessage("Test pipeline."),
        InitQuery(),
        agent,
        ToolsExecutionLoop([gate, agent]),
    ])

    _, _, final_env, _, _ = pipeline.query(
        "Check today's date.",
        FunctionsRuntime(suite.tools),
        env,
    )

    expected_review_outcome = (
        "human_approved" if reviewer_approved else "human_denied"
    )

    assert [record.outcome for record in gate.records] == [
        "auto_approved",
        "auto_denied",
        expected_review_outcome,
        "budget_exhausted_denied",
    ]
    assert [record.executed for record in gate.records] == [
        True, False, reviewer_approved, False
    ]
    assert [record.budget_after for record in gate.records] == [
        1, 1, 0, 0
    ]

    # Rules bypass the downstream policy for the first two calls.
    assert downstream.calls == 2

    # Only one review is permitted by the attention budget.
    assert reviewer.n == 1
    assert gate.budget.remaining == 0

    # The blocked deletion must not change the environment.
    assert final_env.model_dump() == initial_state