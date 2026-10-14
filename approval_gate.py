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
    # LLM tokens spent on THIS tool call (0 when the component did not call an LLM)
    policy_prompt_tokens: int = 0
    policy_completion_tokens: int = 0
    reviewer_prompt_tokens: int = 0
    reviewer_completion_tokens: int = 0


# ---------------------------------------------------------- token accounting
def _components(obj: Any) -> list[Any]:
    """The object plus any policy it wraps (e.g. Member 3's PrefilterPolicy.downstream_policy)."""
    out: list[Any] = []
    while obj is not None and all(obj is not o for o in out):
        out.append(obj)
        obj = getattr(obj, "downstream_policy", None)
    return out


def _clear_usage(obj: Any) -> None:
    for o in _components(obj):
        if hasattr(o, "last_usage"):
            o.last_usage = {}


def _read_usage(obj: Any) -> tuple[int, int]:
    """Components report usage through a `last_usage` dict with prompt_tokens / completion_tokens."""
    p = c = 0
    for o in _components(obj):
        u = getattr(o, "last_usage", None) or {}
        p += int(u.get("prompt_tokens") or 0)
        c += int(u.get("completion_tokens") or 0)
    return p, c


def _new_usage() -> dict[str, dict[str, int]]:
    return {role: {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
            for role in ("agent", "policy", "reviewer")}


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
        self.usage = _new_usage()              # token totals of the CURRENT task
        self._task_open = False

    # called once at the start of every task (by BudgetReset below)
    def start_task(self, **task_meta: Any) -> None:
        if self._task_open:                    # previous task ended abnormally (e.g. API error)
            self.end_task(completed=False)
        self._task_open = True
        self.usage = _new_usage()
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

    def add_agent_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Called by run_real.py for every LLM call the AGENT makes."""
        u = self.usage["agent"]
        u["prompt_tokens"] += prompt_tokens
        u["completion_tokens"] += completion_tokens
        u["calls"] += 1

    def end_task(self, completed: bool = True) -> None:
        """Write one per-task summary line (task_summaries.jsonl, next to the decision log)."""
        if not self._task_open:
            return
        self._task_open = False
        if not self.log_path:
            return
        outcomes = [r.outcome for r in self.records]
        row = {**self.task_meta, "k": self.budget.k, "pipeline_completed": completed,
               "n_tool_calls": len(self.records),
               "n_escalations": sum(o in ("human_approved", "human_denied") for o in outcomes),
               "n_budget_exhausted_denied": outcomes.count("budget_exhausted_denied"),
               "usage": self.usage}
        path = self.log_path.with_name("task_summaries.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def _decide(self, ctx: ToolCallContext) -> tuple[Decision, Outcome, float, float]:
        _clear_usage(self.policy)
        _clear_usage(self.reviewer)
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
            pol_p, pol_c = _read_usage(self.policy)
            rev_p, rev_c = _read_usage(self.reviewer) if reviewer_ms else (0, 0)
            for role, (pt, ct) in (("policy", (pol_p, pol_c)), ("reviewer", (rev_p, rev_c))):
                if pt or ct:
                    self.usage[role]["prompt_tokens"] += pt
                    self.usage[role]["completion_tokens"] += ct
                    self.usage[role]["calls"] += 1
            self._write(GateRecord(
                step_index=self._step, tool_name=tool_call.function, tool_args=dict(tool_call.args),
                policy_decision=decision.value, outcome=outcome.value, executed=executed,
                budget_before=budget_before, budget_after=self.budget.remaining,
                policy_latency_ms=round(policy_ms, 3), reviewer_latency_ms=round(reviewer_ms, 3),
                gate_overhead_ms=round(total_ms - policy_ms - reviewer_ms - exec_ms, 3),
                policy_prompt_tokens=pol_p, policy_completion_tokens=pol_c,
                reviewer_prompt_tokens=rev_p, reviewer_completion_tokens=rev_c))
            self._step += 1
        return query, runtime, env, [*messages, *results], extra_args

    def _write(self, rec: GateRecord) -> None:
        self.records.append(rec)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(json.dumps({**self.task_meta, "k": self.budget.k, **asdict(rec)}, default=str) + "\n")


class TaskEnd(BasePipelineElement):
    """Put this at the END of the pipeline: writes the per-task summary (incl. token usage)."""

    def __init__(self, gate: ApprovalGate) -> None:
        self.gate = gate

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        self.gate.end_task()
        return query, runtime, env, messages, extra_args


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
