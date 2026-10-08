"""Run the gate on the real AgentDojo benchmark (costs money).

API key (set ONE as an environment variable, never write it in a file):
  OPENROUTER_API_KEY  -> calls go through OpenRouter
  OPENAI_API_KEY      -> calls go directly to OpenAI

Example:  python run_real.py --policy full_escalate --k 2 --suite banking --user-task user_task_1
"""
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

from approval_gate import (AlwaysApproveReviewer, ApprovalGate, BudgetReset,
                           FullApprovePolicy, FullEscalatePolicy)

POLICIES = {"full_approve": FullApprovePolicy, "full_escalate": FullEscalatePolicy}


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
    pipeline = AgentPipeline([BudgetReset(gate), system_message, init_query, llm,
                              ToolsExecutionLoop([gate, llm])])
    pipeline.name = name               # attacks need the model name
    return pipeline, gate


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    ap.add_argument("--policy", choices=POLICIES, default="full_escalate")
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--suite", default="banking")
    ap.add_argument("--user-task", action="append", help="e.g. user_task_1 (repeatable); default = all")
    ap.add_argument("--attack", default="important_instructions", help="'none' = no injection")
    ap.add_argument("--logdir", default="runs")
    a = ap.parse_args()

    tag = f"{a.policy}_k{a.k}"
    logdir = Path(a.logdir) / tag
    pipeline, gate = build_pipeline(a.model, POLICIES[a.policy](), AlwaysApproveReviewer(), a.k,
                                    logdir / "gate_decisions.jsonl")
    gate.task_meta.update(policy=a.policy, suite=a.suite, attack=a.attack)
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
