import _paths  # noqa: F401  (sets up imports; see project_paths.py)
import json
from importlib.metadata import version
from time import perf_counter

from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite import get_suite

from approval_gate import ToolCallContext
from rule_prefilter import RulePreFilter


def evaluate_suite(suite_name):
    suite = get_suite("v1.2", suite_name)
    runtime = FunctionsRuntime(suite.tools)
    prefilter = RulePreFilter()

    counts = {"approve": 0, "deny": 0, "defer": 0}
    latencies = []

    for task in suite.user_tasks.values():
        env = suite.load_and_inject_default_environment({})

        # Reference calls are offline fixtures, not live agent proposals.
        # They are not executed, and their labels are not passed to the policy.
        calls = task.ground_truth(env)

        for step_index, call in enumerate(calls):
            context = ToolCallContext(
                tool_name=call.function,
                tool_args=dict(call.args),
                tool_description=runtime.functions[call.function].description,
                task_description=task.PROMPT,
                messages=[],
                step_index=step_index,
                budget_remaining=0,
            )

            start = perf_counter()
            result = prefilter.evaluate(context)
            latencies.append((perf_counter() - start) * 1000)

            decision = (
                result.decision.value
                if result.decision is not None
                else "defer"
            )
            counts[decision] += 1

    total = sum(counts.values())
    covered = counts["approve"] + counts["deny"]

    return {
        "suite": suite_name,
        "reference_tasks": len(suite.user_tasks),
        "reference_calls": total,
        "decisions": counts,
        "coverage_percent": round(100 * covered / total, 2) if total else 0,
        "mean_rule_latency_ms": (
            round(sum(latencies) / len(latencies), 6)
            if latencies else 0
        ),
    }


if __name__ == "__main__":
    suites = ["banking", "slack", "travel", "workspace"]
    results = [evaluate_suite(name) for name in suites]

    total_calls = sum(item["reference_calls"] for item in results)
    total_covered = sum(
        item["decisions"]["approve"] + item["decisions"]["deny"]
        for item in results
    )
    coverage = (
        round(100 * total_covered / total_calls, 2)
        if total_calls else 0
    )

    report = {
        "evaluation_type": "offline_reference_call_coverage",
        "agentdojo_version": version("agentdojo"),
        "configuration": "Default prefilter; no preapproved file permissions.",
        "limitations": (
            "Reference calls are evaluated without execution or history. "
            "This is not live-agent coverage, safety accuracy, or TCR."
        ),
        "total_reference_calls": total_calls,
        "total_covered_calls": total_covered,
        "overall_coverage_percent": coverage,
        "suites": results,
    }

    output_path = _paths.RESULTS_DIR / "member3_reference_coverage.json"
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    for item in results:
        print(
            f"{item['suite']}: "
            f"{item['reference_calls']} reference calls, "
            f"{item['coverage_percent']:.2f}% coverage"
        )

    print(f"Overall coverage: {coverage:.2f}%")
    print(f"Report saved to {output_path}")