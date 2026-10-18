> **Repository layout note (2026-10-18):** files were reorganised by function. Code is in `src/`, tests in `tests/`, runnable scripts in `scripts/`, results in `data/results/`. Renamed: `analyze_member4.py` → `scripts/analyze_results.py`, `member1_integration_guide.md` → `docs/integration_guide.md`, `MEMBER4_SUBMISSION.md` → `docs/member_reports/member4_submission.md`, `data/member4/` → `data/results/member4/`. Run tests from the repository root with `python -m pytest -q`. See the root `README.md`.

# Member 4 integration handoff

This handoff contains Member 4's semantic policy, three prompt variants, offline tests, the preserved 36-row experiment CSV, and the report section. It does not claim completion of the team benchmark.

## Connect to Member 1's runner

```python
from approval_gate import ApprovalGate, BudgetReset
from semantic_adapter import SemanticPolicy

policy = SemanticPolicy(prompt_version="V1")  # V1/V2/V3 are supported
# reviewer = the actual Member 2 reviewer
# k = the runner's chosen per-task escalation budget
# gate = ApprovalGate(policy=policy, reviewer=reviewer, k=k, log_path="gate.jsonl")
```

Use `BudgetReset(gate)` at the start of Member 1's pipeline, and replace the execution-stage `ToolsExecutor` with `gate`. Follow the runner's existing pipeline construction rather than adding a second executor. Do not use `AlwaysApproveReviewer` to claim a secure end-to-end result; it is a placeholder that approves unsafe escalations too.

Create a project virtual environment and install dependencies with `python -m pip install -r requirements.txt`. The offline tests passed in the original environment using Python 3.14.6 and AgentDojo 0.1.35. `requirements.txt` gives direct dependency pins and `requirements-lock.txt` records the installed dependency set. A member using another Python version may need platform-specific dependency resolution.

## Validation

From the repository root, run `python -m pytest tests/test_adapter.py` with the project interpreter. The original five offline adapter test methods passed. For this update, 13 adapter/integration tests passed, including selected-default forwarding, real AgentDojo gateway execution and budget handling. These tests require no API key or paid calls. The original test only checked imports; it has been replaced with meaningful integration checks.

Configure `OPENROUTER_API_KEY` in the local runtime environment for live assessment. Do not put it in source, exported project settings, screenshots, or a submission archive. Errors return escalation; with no budget, the gateway blocks the call.

The full member-1 runner was not present during the original local repair. The repository now contains the runner, but this handoff does not modify its pipeline or claim that semantic-policy benchmark integration has been verified. Preserve the distinction between the package version 0.1.35 and benchmark suite version v1.2.

## Prompt choice

V1: 11/12 exact matches; one ambiguous database change automatically approved.
V2: 9/12; three ambiguous actions denied.
V3: 9/12; three unsafe actions escalated; seven total escalations.

**Selected submission version: V1.** The adapter, direct assessor and `run_real.py` now default to V1. This is an evidence-limited selection: highest development accuracy, fewest development tokens and fewer escalations than V3. V1's T12 auto-approval is a known weakness. The V3 pilot diagnoses excessive escalation; it does not establish V1's AgentDojo superiority. Prompt texts remain unchanged and all versions remain selectable.

For the selected combined policy, use:

```bash
python scripts/run_real.py --policy rules_semantic --prompt-version V1 --k 2 --suite workspace --user-task user_task_0
```

This command is a future paid run, not a run performed for this update. It uses the runner's default `important_instructions` attack. Add `--attack none` for a separate legitimate-task run and set a distinct `--run-id`/output location for repetitions. Do not mistake precheck records for no-attack results.

Read `member4_report_section.md` for the completed selection and pilot analysis. Run `python scripts/analyze_results.py` to recompute all reported counts from the committed data. `data/member4/provenance.json` identifies the original live archive. `sweep_runner.py` increments simulated success unconditionally, so its `sweep_results.json` must not be cited as measured TCR or real API usage. The live archive has no tokens/cost; do not substitute synthetic sweep accounting.

## Paid test boundary

No paid API calls were made during this repair. A one-call live smoke test can use a synthetic context and has a 300-output-token cap per request; one configured retry means up to two attempts. Actual charges depend on the current OpenRouter model/provider rates and metered input/output tokens. A new 36-call experiment can also incur retries and should be budgeted separately. Confirm current pricing and announce a numeric estimate before running either. Existing CSV tokens are usage evidence, not a billing receipt.

