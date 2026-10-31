# Safety Approval Policies for Agent Harnesses

PE6203 Group Project 2. Instructor: Prof. Bo An (CCDS, NTU).

AI agents act through tool calls. Approving every call by hand causes confirmation fatigue, and approving nothing is unsafe. This project adds an **approval gate** to the [AgentDojo](https://github.com/ethz-spylab/agentdojo) benchmark. Before any tool call runs, a policy makes a three-way decision:

- **Approve**: the call runs.
- **Deny**: the call is blocked.
- **Escalate**: a (simulated) human reviewer decides, at most **k** times per task. Once the budget k is spent, any further escalation becomes an automatic deny.

We report the safe task completion rate as a function of the budget (**TCR@k**), the number of human interventions (**HITL load**), and the API cost of each component.

## Repository layout

```
├── README.md
├── requirements.txt / requirements-lock.txt
├── project_paths.py        # makes src/, scripts/ and tests/ importable (used by conftest.py and scripts/)
├── conftest.py             # pytest entry point; loads project_paths.py
│
├── src/
│   ├── gate/               # approval_gate.py (gate + budget), rule_prefilter.py, prefilter_policy.py, semantic_policy.py
│   ├── rules/              # calendar_rules.py
│   ├── adapters/           # semantic_adapter.py (policy ↔ gate), simulated_reviewer.py
│   └── utils/              # tool_metadata.py, prompts.py, cost_tracker.py, cost_report.py
├── tests/                  # all tests (offline, no API key needed)
├── scripts/                # run_real.py, run_experiments.py, sweep_runner.py, analysis_toolkit.py,
│                           # analyze_results.py, evaluate_reference_coverage.py, run_sweep.py, summarize_runs.py,
│                           # plot_results.py, failure_analysis.py
├── docs/                   # group_report.md (+ PDF), integration_guide.md, member_reports/
└── data/
    ├── raw/
    └── results/            # runs/ (experiment logs + AgentDojo traces), analysis/, member4/, ...
```

Modules keep their short import names (`from approval_gate import ApprovalGate`). `project_paths.py` adds the source folders to the import path, so there is no package prefix.

## Setup

Requires Python 3.10 or later.

```bash
pip install -r requirements.txt
```

## Run the tests

From the repository root:

```bash
python -m pytest -q
```

The tests are fully offline: LLM calls are replaced with fakes, so no API key is needed and nothing is charged. They cover:

- The budget state machine, exhaustively for k = 0–3.
- All 97 AgentDojo tasks (339 tool calls): with full-approve, the gated run is identical to plain AgentDojo.
- End-to-end wiring of rules, semantic policy and reviewer.
- Token accounting.

## Run an experiment

Live runs call the model and cost money. Set the key as an environment variable and never write it into a file:

```bash
# PowerShell: $env:OPENROUTER_API_KEY="sk-or-..."
export OPENROUTER_API_KEY=sk-or-...

python scripts/run_real.py --policy rules_semantic --k 2 --suite workspace --user-task user_task_0
```

| Option | Values |
|---|---|
| `--policy` | `full_approve`, `full_escalate` (the two baselines), `rules`, `semantic`, `rules_semantic` |
| `--prompt-version` | `V1` (default), `V2`, `V3`. Used only by the semantic policies |
| `--reviewer` | `simulated` (default), `always_approve` (placeholder only, not valid for security claims) |
| `--k` | escalation budget per task |
| `--suite` / `--user-task` | AgentDojo suite and task(s); omit `--user-task` to run the whole suite |
| `--attack` | `important_instructions` (default) or `none` |
| `--run-id` | repeat index; model output is random, so repeat runs |

Each run writes `data/results/runs/<suite>_<attack>_<policy>_..._k<k>_run<id>/`, which contains:

- **`gate_decisions.jsonl`**: one row per tool call. Fields:
  - `task_id`, `attempt` (AgentDojo may retry a task; the budget carries over), and `tool_call_id`, which matches `call_...` in the trace
  - `step_index`, `message_index`
  - `policy_decision`, `outcome`: `auto_approved`, `auto_denied`, `human_approved`, `human_denied` or `budget_exhausted_denied`
  - `budget_before` / `budget_after`
  - `decided_by`, `policy_reason`, `reviewer_reason`, `final_reason`
  - latencies, and the policy and reviewer token counts
- **`task_summaries.jsonl`**: one row per task, with token usage for the agent, policy and reviewer, and the escalation counts.
- **AgentDojo traces**: one JSON file per task.

Rows with `is_precheck = true` come from AgentDojo running each injection task on its own as a sanity check. They are not benchmark results, so filter them out.

## Main experiment (TCR@k sweep)

```bash
python scripts/run_sweep.py --dry-run     # list the 11 runs: full_approve, full_escalate and rules_semantic (V1) at k = 0,1,2,3,5
python scripts/run_sweep.py               # run what is missing, 3 at a time, then print the results table
python scripts/summarize_runs.py          # rebuild the table (TCR, attack success, HITL load, cost) -> data/results/sweep_summary.csv
python scripts/plot_results.py            # TCR@k curves, HITL and cost figures + Markdown tables -> data/results/figures/
python scripts/failure_analysis.py        # failure classes, representative trajectories, escalation value -> data/results/analysis/
```

The results of the full sweep (Banking, `important_instructions`, gpt-4o-mini, 11 runs) are committed in `data/results/runs/`, and the group report is `docs/group_report.md` (PDF: `docs/group_report.pdf`).

Runs made with the reviewer prompt from before PR #3 are kept in `data/results/archive/` and are not part of the sweep.

## Analyse results

```bash
python src/utils/cost_report.py data/results/runs/*      # cost per component (Member 5's CostTracker)
python scripts/failure_analysis.py                         # failure classes from the gate logs, trajectories, escalation value
python scripts/analysis_toolkit.py                         # Member 6's trace-based analysis
python scripts/analyze_results.py                          # Member 4's prompt-selection analysis
```

`data/results/sweep_results.json` comes from an earlier simulated sweep. Its success counts and token numbers are synthetic, so do not cite it as measured results.

## Team

Group A1.

| Member | Name | Matric no. | NTU email | GitHub | Responsibility | Main files |
|---|---|---|---|---|---|---|
| 1 | Lei Xinjie | G2606932C | LEIX0006@e.ntu.edu.sg | leixinjie02-alt | Gate interceptor & budget manager, AgentDojo integration, logging | `src/gate/approval_gate.py`, `scripts/run_real.py`, `src/utils/cost_report.py` |
| 2 | Zhang Yushuang | G2606425H | YUSHUANG001@e.ntu.edu.sg | zhangyushuang001 | Simulated reviewer & full-escalate baseline | `src/adapters/simulated_reviewer.py` |
| 3 | Cheng Hao | G2606471K | P260013@e.ntu.edu.sg | finnhao9384-max | Rule-based pre-filter & full-approve baseline | `src/gate/rule_prefilter.py`, `src/gate/prefilter_policy.py`, `src/utils/tool_metadata.py`, `src/rules/` |
| 4 | Yang Yisheng | G2604043G | YISHENG005@e.ntu.edu.sg | 18310048236yys-byte | Semantic (LLM) approval policy | `src/gate/semantic_policy.py`, `src/adapters/semantic_adapter.py`, `src/utils/prompts.py` |
| 5 | Luo Ziqi | G2602544H | ZIQI014@e.ntu.edu.sg | lokziqi1018-prog | Experiment sweeps, TCR@k and cost tracking | `scripts/sweep_runner.py`, `src/utils/cost_tracker.py` |
| 6 | Ma Jian | G2606495E | jian011@e.ntu.edu.sg | J-Adrian-Ma | Trajectory parsing & failure classification | `scripts/analysis_toolkit.py`, `data/results/analysis/` |

More detail: `docs/integration_guide.md` and `docs/member_reports/` (e.g. `member1_gateway_architecture.md` for the gate and budget design).
