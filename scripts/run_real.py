"""Run the gate on the real AgentDojo benchmark (costs money).

API key (set ONE as an environment variable, never write it in a file):
  OPENROUTER_API_KEY  -> calls go through OpenRouter
  OPENAI_API_KEY      -> calls go directly to OpenAI

Example:  python scripts/run_real.py --policy full_escalate --k 2 --suite banking --user-task user_task_1
"""
import _paths  # noqa: F401  (sets up imports; see project_paths.py)
import argparse
import os
from pathlib import Path

import openai
from agentdojo.agent_pipeline import (AgentPipeline, InitQuery, OpenAILLM, PipelineConfig,
                                      SystemMessage, ToolsExecutionLoop)
from agentdojo.agent_pipeline.agent_pipeline import load_system_message
from agentdojo.attacks.attack_registry import load_attack
from agentdojo.benchmark import benchmark_suite_with_injections, benchmark_suite_without_injections
from agentdojo.logging import OutputLogger
from agentdojo.task_suite import get_suite

from approval_gate import (AlwaysApproveReviewer, ApprovalGate, BudgetReset, TaskEnd,
                           FullApprovePolicy, FullEscalatePolicy)

POLICIES = ["full_approve", "full_escalate", "rules", "semantic", "rules_semantic"]
REVIEWERS = ["simulated", "always_approve"]


def make_policy(name: str, prompt_version: str = "V1"):
    """full_approve / full_escalate: the two baselines.
    rules:          Member 3 rule prefilter; undecided calls are escalated.
    semantic:       Member 4 LLM semantic policy only.
    rules_semantic: Member 3 rules first; undecided calls go to Member 4's semantic policy."""
    if name == "full_approve":
        return FullApprovePolicy()
    if name == "full_escalate":
        return FullEscalatePolicy()
    from prefilter_policy import PrefilterPolicy      # imported lazily: baselines need no extra files
    from rule_prefilter import RulePreFilter
    if name == "rules":
        return PrefilterPolicy(RulePreFilter(), FullEscalatePolicy())
    from semantic_adapter import SemanticPolicy
    if name == "semantic":
        return SemanticPolicy(prompt_version=prompt_version)
    if name == "rules_semantic":
        return PrefilterPolicy(RulePreFilter(), SemanticPolicy(prompt_version=prompt_version))
    raise ValueError(name)


def make_reviewer(name: str, model: str):
    if name == "simulated":                            # Member 2's LLM-simulated human reviewer
        from simulated_reviewer import SimulatedReviewer
        return SimulatedReviewer(model=model)
    return AlwaysApproveReviewer()                     # placeholder only; not valid for security claims


class UsageCountingClient:
    """Wraps the agent's OpenAI client and reports every completion's token usage to the gate."""

    def __init__(self, client, on_usage):
        self._client, self._on_usage = client, on_usage
        self.chat = self
        self.completions = self

    def create(self, *args, **kwargs):
        resp = self._client.chat.completions.create(*args, **kwargs)
        u = getattr(resp, "usage", None)
        if u is not None:
            self._on_usage(u.prompt_tokens or 0, u.completion_tokens or 0)
        return resp

    def __getattr__(self, name):
        return getattr(self._client, name)


def build_pipeline(model: str, policy, reviewer, k: int, log_path: Path):
    """Standard AgentDojo pipeline, with ToolsExecutor swapped for our ApprovalGate."""
    if os.getenv("OPENROUTER_API_KEY"):
        client = openai.OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1")
        llm = OpenAILLM(client, model if "/" in model else f"openai/{model}")   # OpenRouter ids look like openai/gpt-...
        system_message, init_query = SystemMessage(load_system_message(None)), InitQuery()
        name = model.split("/")[-1]
    else:
        base = AgentPipeline.from_config(PipelineConfig(
            llm=model, model_id=None, defense=None, system_message_name=None, system_message=None))
        system_message, init_query, llm, _old_loop = base.elements
        name = base.name
    gate = ApprovalGate(policy, reviewer, k, log_path=log_path)
    llm.client = UsageCountingClient(llm.client, gate.add_agent_usage)   # agent token accounting
    pipeline = AgentPipeline([BudgetReset(gate), system_message, init_query, llm,
                              ToolsExecutionLoop([gate, llm]), TaskEnd(gate)])
    pipeline.name = name               # attacks need the model name
    return pipeline, gate


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    ap.add_argument("--policy", choices=POLICIES, default="full_escalate")
    ap.add_argument("--prompt-version", choices=["V1", "V2", "V3"], default="V1",
                    help="Member 4 prompt; only used by semantic / rules_semantic")
    ap.add_argument("--reviewer", choices=REVIEWERS, default="simulated")
    ap.add_argument("--run-id", type=int, default=0, help="repeat index (LLM output is random)")
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--suite", default="banking")
    ap.add_argument("--user-task", action="append", help="e.g. user_task_1 (repeatable); default = all")
    ap.add_argument("--attack", default="important_instructions", help="'none' = no injection")
    ap.add_argument("--logdir", default=str(_paths.RESULTS_DIR / "runs"))
    a = ap.parse_args()

    uses_prompt = a.policy in ("semantic", "rules_semantic")
    tag = (f"{a.suite}_{a.attack}_{a.policy}{'_' + a.prompt_version if uses_prompt else ''}"
           f"_{a.reviewer}_k{a.k}_run{a.run_id}")
    logdir = Path(a.logdir) / tag
    for old in ("gate_decisions.jsonl", "task_summaries.jsonl"):   # re-running a config replaces, not appends
        (logdir / old).unlink(missing_ok=True)
    pipeline, gate = build_pipeline(a.model, make_policy(a.policy, a.prompt_version),
                                    make_reviewer(a.reviewer, a.model), a.k, logdir / "gate_decisions.jsonl")
    gate.task_meta.update(policy=a.policy, prompt_version=a.prompt_version if uses_prompt else None,
                          reviewer=a.reviewer, run_id=a.run_id, suite=a.suite, attack=a.attack)
    suite = get_suite("v1.2", a.suite)
    with OutputLogger(str(logdir)):
        if a.attack == "none":
            res = benchmark_suite_without_injections(pipeline, suite, logdir, force_rerun=True,
                                                     user_tasks=a.user_task)
        else:
            res = benchmark_suite_with_injections(pipeline, suite, load_attack(a.attack, suite, pipeline),
                                                  logdir, force_rerun=True, user_tasks=a.user_task)
    u, s = res["utility_results"], res["security_results"]
    line = f"\n{tag}: task completed (utility) {sum(u.values())}/{len(u)}"
    if a.attack != "none":
        line += f"  |  attack succeeded in {sum(s.values())}/{len(s)} runs"
    print(line)
    print(f"gate log -> {logdir / 'gate_decisions.jsonl'}")
    print(f"per-task summaries (tokens, escalations) -> {logdir / 'task_summaries.jsonl'}")
