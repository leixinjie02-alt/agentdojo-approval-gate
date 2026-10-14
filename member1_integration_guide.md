# Member 4 integration handoff

This handoff contains Member 4's semantic policy, three prompt variants, offline tests, the preserved 36-row experiment CSV, and the report section. It does not claim completion of the team benchmark.

## Connect to Member 1's runner

```python
from approval_gate import ApprovalGate, BudgetReset
from semantic_adapter import SemanticPolicy

policy = SemanticPolicy(prompt_version="V3")  # V1/V2/V3 are supported
# reviewer = the actual Member 2 reviewer
# k = the runner's chosen per-task escalation budget
# gate = ApprovalGate(policy=policy, reviewer=reviewer, k=k, log_path="gate.jsonl")
```

Use `BudgetReset(gate)` at the start of Member 1's pipeline, and replace the execution-stage `ToolsExecutor` with `gate`. Follow the runner's existing pipeline construction rather than adding a second executor. Do not use `AlwaysApproveReviewer` to claim a secure end-to-end result; it is a placeholder that approves unsafe escalations too.

Create a project virtual environment and install dependencies with `python -m pip install -r requirements.txt`. The offline tests passed in the original environment using Python 3.14.6 and AgentDojo 0.1.35. `requirements.txt` gives direct dependency pins and `requirements-lock.txt` records the installed dependency set. A member using another Python version may need platform-specific dependency resolution.

## Validation

From the repository root, run `python test_adapter.py` with the project interpreter. Five offline test methods passed, including real AgentDojo gateway execution and budget handling. These tests require no API key or paid calls. The original test only checked imports; it has been replaced with meaningful integration checks.

Configure `OPENROUTER_API_KEY` in the local runtime environment for live assessment. Do not put it in source, exported project settings, screenshots, or a submission archive. Errors return escalation; with no budget, the gateway blocks the call.

The full member-1 runner was not present during the original local repair. The repository now contains the runner, but this handoff does not modify its pipeline or claim that semantic-policy benchmark integration has been verified. Preserve the distinction between the package version 0.1.35 and benchmark suite version v1.2.

## Prompt choice

V1: 11/12 exact matches; one ambiguous database change automatically approved.
V2: 9/12; three ambiguous actions denied.
V3: 9/12; three unsafe actions escalated; seven total escalations.

V3 is retained as the original default, not asserted to be the best-performing prompt. Select the version explicitly in comparative runs. Run broader held-out tests before selecting a final policy.

## Paid test boundary

No paid API calls were made during this repair. A one-call live smoke test can use a synthetic context and has a 300-output-token cap per request; one configured retry means up to two attempts. Actual charges depend on the current OpenRouter model/provider rates and metered input/output tokens. A new 36-call experiment can also incur retries and should be budgeted separately. Confirm current pricing and announce a numeric estimate before running either. Existing CSV tokens are usage evidence, not a billing receipt.
