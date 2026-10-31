"""Results table for every run folder in data/results/runs/: TCR, attack success, HITL load and cost.

    python scripts/summarize_runs.py

Writes data/results/sweep_summary.csv. Pre-check runs (AgentDojo running each injection task on its own)
are excluded; a task that AgentDojo logged twice is counted once.
"""
import _paths  # noqa: F401  (sets up imports; see project_paths.py)

import csv
import json
from pathlib import Path

from cost_tracker import CostTracker


def _attacked_traces(run_dir: Path):
    """utility/security per (user_task, injection_task) from the AgentDojo trace files."""
    out = {}
    for f in run_dir.glob("*/*/*/*/*.json"):
        if f.parent.name == "none":                     # pre-check or no-attack runs
            continue
        t = json.loads(f.read_text(encoding="utf-8"))
        out[(t["user_task_id"], t.get("injection_task_id"))] = (bool(t["utility"]), bool(t["security"]))
    return out


def _summaries(run_dir: Path):
    rows = {}
    p = run_dir / "task_summaries.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if not r.get("is_precheck"):
                rows[(r["user_task_id"], r.get("injection_task_id"))] = r   # last row wins (dedupe)
    return rows


def summarise(runs_dir: Path):
    table = []
    for run_dir in sorted(d for d in Path(runs_dir).iterdir() if d.is_dir()):
        summ = _summaries(run_dir)
        traces = _attacked_traces(run_dir)
        if not summ:
            continue
        any_row = next(iter(summ.values()))
        tracker = CostTracker()
        for r in summ.values():
            for role, u in r["usage"].items():
                if u["calls"]:
                    tracker.log_api_call(role, u["prompt_tokens"], u["completion_tokens"])
                    tracker.usage[role]["calls"] += u["calls"] - 1
        cost = tracker.calculate_cost("gpt-4o-mini")
        n = len(traces)
        safe = sum(u and not s for u, s in traces.values())
        attacks = sum(s for _, s in traces.values())
        hitl_all = sum(r["n_escalations"] for r in summ.values())
        hitl_ok = sum(r["n_escalations"] for key, r in summ.items() if traces.get(key, (False, True)) == (True, False))
        table.append({
            "run": run_dir.name, "policy": any_row.get("policy"), "prompt": any_row.get("prompt_version") or "",
            "k": any_row.get("k"), "attacked_runs": n,
            "TCR": round(safe / n, 4) if n else "", "safe_completed": safe,
            "attack_success_rate": round(attacks / n, 4) if n else "",
            "HITL_load_completed_tasks": hitl_ok, "HITL_load_all_tasks": hitl_all,
            "cost_agent_usd": cost["breakdown"]["agent"]["cost_usd"],
            "cost_policy_usd": cost["breakdown"]["policy"]["cost_usd"],
            "cost_reviewer_usd": cost["breakdown"]["reviewer"]["cost_usd"],
            "cost_total_usd": cost["total_cost_usd"],
        })
    if not table:
        print("No finished runs found.")
        return []
    out = _paths.RESULTS_DIR / "sweep_summary.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    print(f"\n{'policy':16s}{'prompt':7s}{'k':>3s}{'runs':>6s}{'TCR':>8s}{'ASR':>8s}{'HITL(ok)':>10s}{'cost $':>9s}")
    for r in sorted(table, key=lambda r: (r["policy"] or "", r["k"] or 0)):
        print(f"{r['policy']:16s}{r['prompt']:7s}{r['k']:>3}{r['attacked_runs']:>6}{r['TCR']:>8}"
              f"{r['attack_success_rate']:>8}{r['HITL_load_completed_tasks']:>10}{r['cost_total_usd']:>9}")
    print(f"\nSaved {out}")
    return table


if __name__ == "__main__":
    summarise(_paths.RESULTS_DIR / "runs")
