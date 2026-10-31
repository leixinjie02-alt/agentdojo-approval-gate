> **Draft (31 Oct 2026):** Sections 6–10 are filled in once the TCR@k sweep finishes.

# Safety Approval Policies for Agent Harnesses

**PE6203 Group Project 2 — Group A1**

Instructor: Prof. Bo An (CCDS, NTU)

| Member | Name | Responsibility |
|---|---|---|
| 1 | Lei Xinjie | Approval gate, budget controller, AgentDojo integration, logging, experiment runner |
| 2 | Zhang Yushuang | Simulated human reviewer, full-escalate baseline |
| 3 | Cheng Hao | Rule-based pre-filter, tool metadata, full-approve baseline |
| 4 | Yang Yisheng | Semantic (LLM) approval policy and prompt selection |
| 5 | Luo Ziqi | Experiment sweeps, TCR@k and cost tracking |
| 6 | Ma Jian | Trajectory parsing, failure classification, escalation-value analysis |

Code, logs and traces: <https://github.com/leixinjie02-alt/agentdojo-approval-gate>. Detailed component write-ups are in `docs/member_reports/`.

---

## Abstract

{{ABSTRACT}}

---

## 1. Introduction

An AI agent acts on the world through tool calls: it reads files, sends money, changes passwords. Each call can be checked before it runs, but the two obvious policies both fail. Asking a human about every call produces confirmation fatigue, and the brief cites Anthropic's observation that 93% of such prompts are approved without real scrutiny. Approving every call automatically leaves the agent exposed to prompt injection and to its own mistakes.

The project asks for a policy in between. For every proposed tool call the policy chooses one of three actions: **auto-approve** (run it), **auto-deny** (block it), or **escalate** (ask a human, who approves or denies). Human attention is limited to a budget of **k escalations per task**; once it is spent, any further escalation becomes an automatic denial. The goal is to maximise **TCR@k**, the fraction of tasks the agent completes without executing any unauthorised call, while keeping the **HITL load**, the number of escalations in successfully completed tasks, low.

We built the approval gate into the AgentDojo benchmark, implemented a two-stage policy (deterministic rules followed by an LLM risk assessor), implemented both required baselines and an LLM-simulated reviewer, and evaluated them on the AgentDojo Banking suite under the `important_instructions` prompt-injection attack for k ∈ {0, 1, 2, 3, 5}.

Our contributions are:

1. A policy-agnostic **approval gate** that intercepts every tool call inside AgentDojo, enforces the per-task budget (including across AgentDojo's automatic retries), and logs every decision with its reason, cost and a join key into the benchmark trace (Section 2).
2. A **two-stage approval policy**: trusted rules resolve narrow cases for free, and a GPT-4o-mini semantic assessor decides the rest (Section 3).
3. A **simulated reviewer** with an explicit trust boundary between the user's request and untrusted tool output (Section 4).
4. A matched **TCR@k sweep** against both baselines, with HITL load and per-component API cost (Sections 5–6), and a **failure and escalation-value analysis** of the resulting trajectories (Sections 7–8).

## 2. Approval gate and budget controller

*Detail: `docs/member_reports/member1_gateway_architecture.md`.*

### 2.1 Integration point

In AgentDojo an agent is a pipeline of elements. Inside the tool loop, the LLM proposes tool calls and a single element, `ToolsExecutor`, runs them against the task environment. Our `ApprovalGate` is a **subclass of `ToolsExecutor`** that replaces it. For each proposed call it consults the policy and passes only approved calls to the original executor. A blocked call is not run; the agent receives the tool error "Tool call blocked by the approval policy" and may continue by other means. Because the gate *is* the executor, no tool call can bypass it, and no benchmark code, task, environment or scoring function is modified. Two small elements bracket each task: `BudgetReset` refills the budget at the start and `TaskEnd` writes a per-task summary at the end.

```
BudgetReset → system message → user query → Agent LLM
            → [ ApprovalGate ⇄ Agent LLM ]  (tool loop, until a final answer)
            → TaskEnd
```

### 2.2 Decision flow and budget

| Policy says | Budget | Result | Outcome label |
|---|---|---|---|
| APPROVE | – | executed | `auto_approved` |
| DENY | – | blocked | `auto_denied` |
| ESCALATE | k_remaining > 0 | spend 1; reviewer approves → executed | `human_approved` |
| ESCALATE | k_remaining > 0 | spend 1; reviewer denies → blocked | `human_denied` |
| ESCALATE | k_remaining = 0 | blocked without asking the reviewer | `budget_exhausted_denied` |

The budget is spent when a call is escalated, whatever the reviewer decides, because the human's attention is used either way. Auto-approve and auto-deny never touch it.

**What the policy and reviewer see.** Only information a real reviewer would have: the tool name, arguments and description, the user's task text, the message history so far and the step index. Ground-truth labels, the injection-task identity and attack annotations are never placed in the context; an integration test checks that none of them reaches the reviewer's prompt.

**AgentDojo retries.** AgentDojo re-runs a task (up to three attempts, same environment) when the agent gives no final answer, which happens often once the budget is spent and the agent keeps retrying blocked calls. Our first version refilled the budget on every attempt, so one task could receive up to 3k escalations. We found this in the first full log (one task used 4 escalations at k = 2). The gate now detects a retry of the same task, carries the remaining budget over and labels each log row with its `attempt`. All results in this report were produced after the fix.

### 2.3 Logs and verification

Each run writes `gate_decisions.jsonl` (one row per tool call: task, attempt, `tool_call_id` matching the trace, policy decision, outcome, budget before/after, policy and reviewer reasons, latencies and token counts) and `task_summaries.jsonl` (one row per task: escalations, budget-exhausted denials, attempts, and agent/policy/reviewer token usage). The agent's tokens are counted by wrapping its LLM client.

The gate is covered by offline tests that need no API key (73 tests in total in the repository):

- the budget state machine for every sequence of four decisions × every reviewer answer, k = 0–3, against an independent reference implementation;
- transparency: all 97 AgentDojo user tasks (339 tool calls, four suites) replayed through the gate with full-approve give messages and final environments identical to plain AgentDojo;
- blocking: with k = 0 and full-escalate, or with deny-all, no call executes and the environment is unchanged;
- rules → semantic → reviewer routing, join keys, reasons, token accounting, and the retry case using AgentDojo's real `run_task_with_pipeline`.

On a 684-call live run, all four budget invariants held on every row, and the gate's own overhead was 0.06 ms per call on average, against a median of 0.91 s for one reviewer call.

## 3. Our approval policy: rules, then semantic assessment

The policy (`rules_semantic`) has two stages. The rule pre-filter decides narrow, well-specified cases at no API cost; every call it cannot resolve goes to the semantic assessor. Only an `ESCALATE` from the assessor reaches the reviewer and spends budget.

### 3.1 Rule pre-filter

*Detail: `docs/member_reports/member3_report_section.md`.*

`RulePreFilter` returns APPROVE, DENY or *no decision*. Its rules, in order, are: deny any tool on a trusted block list; approve `get_current_day` with no arguments; approve `get_day_calendar_events` when its `day` matches an explicit date in the user's request; approve `get_file_by_id` when the file is on a trusted per-task allow list. A call that matches no rule is passed on, never approved by default: read-only status alone is not treated as authorisation. The tool metadata (read-only, resource scope, destructive) covers all 24 Workspace tools.

The rules are deliberately narrow. On AgentDojo's reference solutions they resolve 3 of 339 calls (all in Workspace) and none in Banking. **In the Banking experiments below, the pre-filter therefore resolves no calls, and `rules_semantic` behaves as the semantic assessor alone.** We report it under its full name because that is the configuration that was run.

### 3.2 Semantic risk assessor

*Detail: `docs/member_reports/member4_report_section.md`.*

The assessor asks GPT-4o-mini (temperature 0, JSON output, at most 300 output tokens) to choose `auto_approve`, `auto_deny` or `escalate` from the user's request, the tool name and arguments, the tool's metadata and the agent's previous actions. Tool arguments and history are declared untrusted, and the model is told not to follow instructions embedded in them. API errors, unparsable output and invalid decisions fall back to `escalate`, so a failure of the assessor can never become an automatic approval.

Three prompts were compared on a hand-written set of 12 cases (4 safe, 4 unsafe, 4 ambiguous):

| Prompt | Exact matches | Unsafe correctly denied | Ambiguous correctly escalated | Escalation rate | Total tokens |
|---|---|---|---|---|---|
| V1 (general principles) | 11/12 | 4/4 | 3/4 | 25.0% | 4,174 |
| V2 (structured, stricter) | 9/12 | 4/4 | 1/4 | 8.3% | 4,539 |
| V3 (escalate when uncertain) | 9/12 | 1/4 | 4/4 | 58.3% | 5,258 |

**V1 was selected.** V3 handled ambiguity best but passed three clearly unsafe cases to the reviewer, and in a live Workspace pilot it escalated all 42 read-only calls it saw, so 27 later calls were blocked only because the budget had run out. V2 denied ambiguous cases a reviewer could have approved. V1's known weakness — it auto-approved a bulk database update labelled "escalate" — is kept visible. The 12-case set is small and has empty histories, so this choice is an engineering judgement, not a statistical ranking; the sweep below is the first end-to-end measurement of V1.

## 4. Baselines and simulated reviewer

*Detail: `docs/member_reports/member2_reviewer_design.md`.*

**Full-approve** returns APPROVE for every call: unguarded execution, zero escalations, zero policy and reviewer cost, independent of k. **Full-escalate** returns ESCALATE for every call: the first k calls of each task go to the reviewer and every later call is denied by budget exhaustion.

**Simulated reviewer.** `SimulatedReviewer` asks GPT-4o-mini (temperature 0, JSON output) for `approve` or `deny` with a short reason. It receives the user's task, the tool name, description and arguments, the step index and the 12 most recent messages, with long fields truncated. Malformed output, an invalid decision or an API error is treated as **deny**, so a reviewer failure never becomes an authorisation.

Its prompt (merged as PR #3) draws an explicit **trust boundary**: only the user's original request can authorise an action. Retrieved files, transaction descriptions and other tool outputs may provide data but cannot authorise new actions, so a password change or payment requested only by a retrieved notice must be denied. In response to an earlier analysis showing many legitimate reads being blocked, the prompt also states that relevant preparatory reads (balance, transactions, user info) may be approved even if the user did not name them, while irrelevant or excessive reads are still denied. Runs made with the earlier prompt are archived in `data/results/archive/` and are not used in this report.

## 5. Experimental setup

| Setting | Value |
|---|---|
| Benchmark | AgentDojo 0.1.35, suite `banking` (16 user tasks × 9 injection tasks) |
| Attack | `important_instructions` |
| Agent, policy and reviewer model | `gpt-4o-mini-2024-07-18` via OpenRouter |
| Policies | full-approve; full-escalate, k ∈ {0,1,2,3,5}; rules + semantic (V1), k ∈ {0,1,2,3,5} |
| Repeats | one run (run 0) per configuration |
| Command | `python scripts/run_sweep.py` (11 runs) → `summarize_runs.py` → `plot_results.py` |

**Metrics.**

- A run of one (user task, injection task) pair is a **safe completion** when AgentDojo's utility check passes and its security check fails, i.e. the user task was done and the attacker's goal was not reached. **TCR@k** = safe completions / 144 attacked runs. We give 95% Wilson intervals.
- **Attack success rate (ASR)** = runs in which the attacker's goal was reached / 144.
- **HITL load** follows the brief: the total number of escalations across safely completed runs. We also report escalations across all runs, which is what the reviewer actually has to handle.
- **API cost** is computed from the token counts logged per component (agent, policy, reviewer) at GPT-4o-mini prices ($0.15 per million input tokens, $0.60 per million output tokens).

AgentDojo also runs each injection task once on its own as a sanity check; these 9 "pre-check" runs per configuration are excluded from every metric.

## 6. Results

{{RESULTS}}

## 7. Failure analysis

{{FAILURES}}

## 8. Escalation-value analysis

{{ESCALATION}}

## 9. Discussion and limitations

{{DISCUSSION}}

## 10. Conclusion

{{CONCLUSION}}

## Appendix A. Reproducing the results

```bash
pip install -r requirements.txt
python -m pytest -q                       # offline, no API key needed
export OPENROUTER_API_KEY=sk-or-...       # PowerShell: $env:OPENROUTER_API_KEY="sk-or-..."
python scripts/run_sweep.py               # 11 runs, about 1–2 hours and about US$2
python scripts/summarize_runs.py          # data/results/sweep_summary.csv
python scripts/plot_results.py            # data/results/figures/
python scripts/analysis_toolkit.py        # failure classes and escalation value
```

Raw logs and AgentDojo traces for every run are in `data/results/runs/`.
