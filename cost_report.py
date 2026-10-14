"""Connect the gate's token logs to Member 5's CostTracker.

Reads task_summaries.jsonl written by run_real.py and prints Member 5's cost table.

Usage:
    python cost_report.py runs/<run_folder>               # one run
    python cost_report.py runs/*                          # several runs, one table each
    python cost_report.py runs/<run_folder> --include-precheck
"""
import argparse
import json
from pathlib import Path

from cost_tracker import CostTracker


def tracker_from_run(run_dir: Path, include_precheck: bool = False) -> tuple[CostTracker, int]:
    tracker = CostTracker()
    n_tasks = 0
    path = Path(run_dir) / "task_summaries.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("is_precheck") and not include_precheck:
            continue   # AgentDojo's sanity runs of the injection tasks are not benchmark results
        n_tasks += 1
        for role, u in row["usage"].items():
            if u["calls"]:
                # CostTracker counts one call per log_api_call; split the totals evenly across calls
                tracker.log_api_call(role, u["prompt_tokens"], u["completion_tokens"])
                tracker.usage[role]["calls"] += u["calls"] - 1
    return tracker, n_tasks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--model", default="gpt-4o-mini", help="pricing key in CostTracker.model_prices")
    ap.add_argument("--include-precheck", action="store_true")
    a = ap.parse_args()
    for d in a.run_dirs:
        if not (Path(d) / "task_summaries.jsonl").exists():
            print(f"skip {d}: no task_summaries.jsonl (run made before token logging was added?)")
            continue
        tracker, n = tracker_from_run(Path(d), a.include_precheck)
        print(f"\n{d}: {n} task runs")
        tracker.print_summary(model_name=a.model)
