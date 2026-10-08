"""Approval gate for AgentDojo (Member 1: Harness Interceptor & Budget Manager).

Drop-in replacement for AgentDojo's ToolsExecutor. Every tool call is intercepted
BEFORE execution, routed through an approval policy, and (if escalated) through a
human reviewer, subject to a per-task escalation budget k.
"""
from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from agentdojo.agent_pipeline import BasePipelineElement, ToolsExecutor
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionCall, FunctionsRuntime
from agentdojo.logging import Logger
from agentdojo.types import ChatMessage, ChatToolResultMessage, text_content_block_from_string


# ---------------------------------------------------------------- interfaces
class Decision(str, Enum):
    APPROVE = "approve"    # auto-approve
    DENY = "deny"          # auto-deny
    ESCALATE = "escalate"  # ask the human reviewer


@dataclass
class ToolCallContext:
    """Everything a policy / reviewer may look at for ONE tool call."""
    tool_name: str
    tool_args: dict[str, Any]
    tool_description: str            # docstring of the tool (metadata)
    task_description: str            # the user's original request
    messages: Sequence[ChatMessage]  # full history so far (trace + conversation)
    step_index: int                  # 0-based index of this tool call within the task
    budget_remaining: int            # escalations still available BEFORE this call


class ApprovalPolicy(Protocol):      # Members 2/3/4 implement this
    def decide(self, ctx: ToolCallContext) -> Decision: ...


class Reviewer(Protocol):            # Member 2 implements this
    def review(self, ctx: ToolCallContext) -> bool: ...   # True = approve


# ------------------------------------------------------------- budget logic
class Outcome(str, Enum):
    AUTO_APPROVED = "auto_approved"
    AUTO_DENIED = "auto_denied"
    HUMAN_APPROVED = "human_approved"
    HUMAN_DENIED = "human_denied"
    BUDGET_EXHAUSTED_DENIED = "budget_exhausted_denied"


class BudgetManager:
    """Per-task escalation budget k. State: ACTIVE (remaining > 0) -> EXHAUSTED (remaining == 0)."""

    def __init__(self, k: int) -> None:
        if k < 0:
            raise ValueError("k must be >= 0")
        self.k = k
        self.remaining = k

    def reset(self) -> None:
        self.remaining = self.k

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0

    def try_consume(self) -> bool:
        """Spend one escalation. Returns False (and spends nothing) if exhausted."""
        if self.exhausted:
            return False
        self.remaining -= 1
        return True


@dataclass
class GateRecord:
    """One line of the decision log (consumed by Members 5 and 6)."""
    step_index: int
    tool_name: str
    tool_args: dict[str, Any]
    policy_decision: str
    outcome: str
    executed: bool
    budget_before: int
    budget_after: int
    policy_latency_ms: float
    reviewer_latency_ms: float
    gate_overhead_ms: float  # gate bookkeeping only, excluding policy/reviewer/tool time


# ------------------------------------------------------------------ the gate
class ApprovalGate(ToolsExecutor):
    """Intercepts each tool call before execution and routes it through the policy."""

    DENY_MSG = "Tool call blocked by the approval policy. Do not retry this call."

    def __init__(self, policy: ApprovalPolicy, reviewer: Reviewer, k: int,
                 log_path: str | Path | None = None) -> None:
        super().__init__()
        self.policy = policy
        self.reviewer = reviewer
        self.budget = BudgetManager(k)
        self.log_path = Path(log_path) if log_path else None
        self.records: list[GateRecord] = []   # records of the CURRENT task
        self.task_meta: dict[str, Any] = {}
        self._step = 0

    # called once at the start of every task (by BudgetReset below)
    def start_task(self, **task_meta: Any) -> None:
        self.budget.reset()
        self.records = []
        self._step = 0
        # AgentDojo's benchmark keeps the current task in its logger context; copy the IDs so that
        # every log line says which (user task, injection task, attack) it belongs to.
        ctx = getattr(Logger.get(), "context", None) or {}
        user_task_id = ctx.get("user_task_id")
        self.task_meta.update(
            suite=ctx.get("suite_name", self.task_meta.get("suite")),
            user_task_id=user_task_id,
            injection_task_id=ctx.get("injection_task_id"),
            attack=ctx.get("attack_type", self.task_meta.get("attack")),
            # Before the attacked runs, AgentDojo runs each injection task on its own as a sanity
            # check. Those runs are NOT benchmark results: filter them out with is_precheck.
            is_precheck=bool(user_task_id) and str(user_task_id).startswith("injection_task"),
        )
        self.task_meta.update(task_meta)

    def _decide(self, ctx: ToolCallContext) -> tuple[Decision, Outcome, float, float]:
        t0 = time.perf_counter()
        decision = Decision(self.policy.decide(ctx))
        policy_ms = (time.perf_counter() - t0) * 1000
        reviewer_ms = 0.0
        if decision is Decision.APPROVE:
            outcome = Outcome.AUTO_APPROVED
        elif decision is Decision.DENY:
            outcome = Outcome.AUTO_DENIED
        elif not self.budget.try_consume():          # ESCALATE but k exhausted
            outcome = Outcome.BUDGET_EXHAUSTED_DENIED
        else:
            t1 = time.perf_counter()
            approved = self.reviewer.review(ctx)
            reviewer_ms = (time.perf_counter() - t1) * 1000
            outcome = Outcome.HUMAN_APPROVED if approved else Outcome.HUMAN_DENIED
        return decision, outcome, policy_ms, reviewer_ms

    def query(self, query: str, runtime: FunctionsRuntime, env: Env = EmptyEnv(),
              messages: Sequence[ChatMessage] = [], extra_args: dict = {}):
        if not messages or messages[-1]["role"] != "assistant" or not messages[-1]["tool_calls"]:
            return query, runtime, env, messages, extra_args

        results: list[ChatMessage] = []
        for tool_call in messages[-1]["tool_calls"]:
            t_start = time.perf_counter()
            fn = runtime.functions.get(tool_call.function)
            ctx = ToolCallContext(
                tool_name=tool_call.function,
                tool_args=dict(tool_call.args),
                tool_description=fn.description if fn else "",
                task_description=query,
                messages=[*messages, *results],
                step_index=self._step,
                budget_remaining=self.budget.remaining,
            )
            budget_before = self.budget.remaining
            decision, outcome, policy_ms, reviewer_ms = self._decide(ctx)
            executed = outcome in (Outcome.AUTO_APPROVED, Outcome.HUMAN_APPROVED)

            exec_ms = 0.0
            if executed:
                # Reuse AgentDojo's own executor for exactly this one call.
                t_exec = time.perf_counter()
                single = [*messages[:-1], {**messages[-1], "tool_calls": [tool_call]}]
                _, runtime, env, out, _ = super().query(query, runtime, env, single, extra_args)
                exec_ms = (time.perf_counter() - t_exec) * 1000
                results.append(out[-1])
            else:
                results.append(ChatToolResultMessage(
                    role="tool", content=[text_content_block_from_string("")],
                    tool_call_id=tool_call.id, tool_call=tool_call, error=self.DENY_MSG))

            total_ms = (time.perf_counter() - t_start) * 1000
            self._write(GateRecord(
                step_index=self._step, tool_name=tool_call.function, tool_args=dict(tool_call.args),
                policy_decision=decision.value, outcome=outcome.value, executed=executed,
                budget_before=budget_before, budget_after=self.budget.remaining,
                policy_latency_ms=round(policy_ms, 3), reviewer_latency_ms=round(reviewer_ms, 3),
                gate_overhead_ms=round(total_ms - policy_ms - reviewer_ms - exec_ms, 3)))
            self._step += 1
        return query, runtime, env, [*messages, *results], extra_args

    def _write(self, rec: GateRecord) -> None:
        self.records.append(rec)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(json.dumps({**self.task_meta, "k": self.budget.k, **asdict(rec)}, default=str) + "\n")


class BudgetReset(BasePipelineElement):
    """Put this at the START of the pipeline: it runs once per task and refills the budget."""

    def __init__(self, gate: ApprovalGate) -> None:
        self.gate = gate

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        self.gate.start_task()
        return query, runtime, env, messages, extra_args


# ------------------------------------------------- trivial policies / reviewers
class FullApprovePolicy:
    def decide(self, ctx): return Decision.APPROVE

class FullEscalatePolicy:
    def decide(self, ctx): return Decision.ESCALATE

class AlwaysApproveReviewer:   # placeholder until Member 2's LLM reviewer is ready
    def review(self, ctx): return True
