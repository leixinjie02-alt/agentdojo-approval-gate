"""Figures and tables for the report, built from data/results/sweep_summary.csv.

    python scripts/summarize_runs.py     # first: build the summary table from the run folders
    python scripts/plot_results.py

Writes to data/results/figures/:
  tcr_at_k.png          TCR@k for our policy and both baselines (95% Wilson intervals)
  tcr_action_at_k.png   the same on the tasks that need the agent to act (see summarize_runs.py)
  asr_at_k.png          attack success rate against k
  hitl_at_k.png         human escalations per task against k
  cost_by_component.png API cost per component (agent / policy / reviewer) for each run
  results_tables.md     the same numbers as Markdown tables, ready to paste into the report
"""
import _paths  # noqa: F401  (sets up imports; see project_paths.py)

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LABELS = {
    "full_approve": "Full-approve (baseline)",
    "full_escalate": "Full-escalate (baseline)",
    "rules_semantic": "Rules + semantic (ours)",
    "rules": "Rules only",
    "semantic": "Semantic only",
}
COLORS = {"full_approve": "#9a9a9a", "full_escalate": "#d1495b", "rules_semantic": "#00798c",
          "rules": "#edae49", "semantic": "#66a182"}
ORDER = ["full_approve", "full_escalate", "rules_semantic", "rules", "semantic"]


def wilson(k, n, z=1.96):
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for key in ("k", "attacked_runs", "safe_completed", "HITL_load_completed_tasks", "HITL_load_all_tasks",
                        "action_task_runs", "safe_completed_action_tasks"):
                r[key] = int(r[key])
            for key in ("TCR", "TCR_action_tasks", "attack_success_rate", "cost_agent_usd", "cost_policy_usd",
                        "cost_reviewer_usd", "cost_total_usd"):
                r[key] = float(r[key])
            rows.append(r)
    return rows


def by_policy(rows):
    out = {}
    for r in rows:
        out.setdefault(r["policy"], []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r["k"])
    return {p: out[p] for p in ORDER if p in out}


def _k_axis(ax, ks, ylabel):
    ax.set_xticks(ks)
    ax.set_xlabel("Escalation budget k (per task)")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3)
    ax.legend(frameon=False, fontsize=9)


CI_COUNTS = {"TCR": ("safe_completed", "attacked_runs"),
             "TCR_action_tasks": ("safe_completed_action_tasks", "action_task_runs")}


def line_plot(groups, ks, metric, ylabel, out, ci=False):
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for pol, rs in groups.items():
        c = COLORS.get(pol, None)
        if len(rs) == 1 and pol == "full_approve":       # k does not apply: draw a reference line
            v = rs[0][metric]
            ax.axhline(v, color=c, ls="--", label=f"{LABELS[pol]} = {v:.3f}")
            if ci:
                num, den = CI_COUNTS[metric]
                lo, hi = wilson(rs[0][num], rs[0][den])
                ax.axhspan(lo, hi, color=c, alpha=0.12)
            continue
        x = [r["k"] for r in rs]
        y = [r[metric] for r in rs]
        ax.plot(x, y, marker="o", color=c, label=LABELS.get(pol, pol))
        if ci:
            num, den = CI_COUNTS[metric]
            b = [wilson(r[num], r[den]) for r in rs]
            ax.fill_between(x, [lo for lo, _ in b], [hi for _, hi in b], color=c, alpha=0.15)
    if metric != "hitl":
        ax.set_ylim(bottom=0)
    _k_axis(ax, ks, ylabel)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def cost_plot(groups, out):
    names, parts = [], {"agent": [], "policy": [], "reviewer": []}
    for pol, rs in groups.items():
        for r in rs:
            short = {"full_approve": "FA", "full_escalate": "FE", "rules_semantic": "Ours"}.get(pol, pol)
            names.append(f"{short}\nk={r['k']}" if pol != "full_approve" else short)
            for comp in parts:
                parts[comp].append(r[f"cost_{comp}_usd"])
    fig, ax = plt.subplots(figsize=(max(6.4, 0.6 * len(names)), 4))
    bottom = [0.0] * len(names)
    for comp, color in (("agent", "#30638e"), ("policy", "#00798c"), ("reviewer", "#d1495b")):
        ax.bar(names, parts[comp], bottom=bottom, color=color, label=comp)
        bottom = [b + v for b, v in zip(bottom, parts[comp])]
    ax.set_ylabel("API cost per run (USD, gpt-4o-mini)")
    ax.set_xlabel("FA = full-approve, FE = full-escalate, Ours = rules + semantic")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    plt.setp(ax.get_xticklabels(), fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def tables(groups):
    lines = ["## TCR@k, attack success and HITL load", "",
             "| Policy | k | Attacked runs | Safe completions | TCR@k (95% CI) | TCR@k, action tasks (95% CI) | Attack success | "
             "Escalations, all tasks | Escalations per task | Escalations in safely completed tasks |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for pol, rs in groups.items():
        for r in rs:
            lo, hi = wilson(r["safe_completed"], r["attacked_runs"])
            n = r["attacked_runs"] or 1
            alo, ahi = wilson(r["safe_completed_action_tasks"], r["action_task_runs"])
            lines.append(f"| {LABELS.get(pol, pol)} | {r['k'] if pol != 'full_approve' else '–'} | {r['attacked_runs']} | "
                         f"{r['safe_completed']} | {r['TCR']:.3f} ({lo:.3f}–{hi:.3f}) | "
                         f"{r['TCR_action_tasks']:.3f} ({alo:.3f}–{ahi:.3f}) | {r['attack_success_rate']:.3f} | "
                         f"{r['HITL_load_all_tasks']} | {r['HITL_load_all_tasks'] / n:.2f} | "
                         f"{r['HITL_load_completed_tasks']} |")
    lines += ["", "## API cost per component (USD per run)", "",
              "| Policy | k | Agent | Policy | Reviewer | Total | Cost per safe completion |",
              "|---|---|---|---|---|---|---|"]
    for pol, rs in groups.items():
        for r in rs:
            per = r["cost_total_usd"] / r["safe_completed"] if r["safe_completed"] else float("nan")
            lines.append(f"| {LABELS.get(pol, pol)} | {r['k'] if pol != 'full_approve' else '–'} | "
                         f"{r['cost_agent_usd']:.4f} | {r['cost_policy_usd']:.4f} | {r['cost_reviewer_usd']:.4f} | "
                         f"{r['cost_total_usd']:.4f} | {per:.4f} |")
    return "\n".join(lines) + "\n"


def main():
    src = _paths.RESULTS_DIR / "sweep_summary.csv"
    if not src.exists():
        raise SystemExit("Run scripts/summarize_runs.py first.")
    rows = load(src)
    for r in rows:
        r["hitl"] = r["HITL_load_all_tasks"] / (r["attacked_runs"] or 1)
    groups = by_policy(rows)
    ks = sorted({r["k"] for r in rows})
    out = Path(_paths.RESULTS_DIR / "figures")
    out.mkdir(parents=True, exist_ok=True)
    line_plot(groups, ks, "TCR", "TCR@k (safe task completion rate)", out / "tcr_at_k.png", ci=True)
    line_plot(groups, ks, "TCR_action_tasks", "TCR@k on the 12 tasks that need an action",
              out / "tcr_action_at_k.png", ci=True)
    line_plot(groups, ks, "attack_success_rate", "Attack success rate", out / "asr_at_k.png")
    line_plot({p: v for p, v in groups.items() if p != "full_approve"}, ks, "hitl",
              "Human escalations per task", out / "hitl_at_k.png")
    cost_plot(groups, out / "cost_by_component.png")
    (out / "results_tables.md").write_text(tables(groups), encoding="utf-8")
    print(f"Saved figures and tables to {out}")


if __name__ == "__main__":
    main()
