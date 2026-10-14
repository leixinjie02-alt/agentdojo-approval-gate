# Member 3 Rule-Based Prefilter

## Purpose

This module performs deterministic checks before the downstream
approval policy. It approves narrowly defined low-risk calls,
denies explicitly prohibited tools, and defers other calls.

## Files

- `tool_metadata.py`: Trusted metadata for all 24 Workspace tools.
- `test_tool_metadata.py`: Registry coverage and read-state mutation checks.
- `rule_prefilter.py`: Rule evaluation and task-scoped permissions.
- `prefilter_policy.py`: Adapter compatible with the approval gate.
- `test_rule_prefilter.py`: Rule and permission boundary tests.
- `test_prefilter_policy.py`: Offline AgentDojo integration tests.

## Implemented Rules

1. Deny tools explicitly blocked by trusted configuration.
2. Approve `get_current_day` when no arguments are supplied.
3. Approve `get_file_by_id` only when:
   - The metadata identifies it as a read-only tool.
   - The arguments contain exactly one string-valued `file_id`.
   - That file ID is approved for the original user request.
4. Defer all other calls to the downstream policy.

File-read permission does not authorize sharing or deleting the file.
Permissions must not come from attack content or benchmark oracle labels.

## Integration

```python
from approval_gate import FullEscalatePolicy
from prefilter_policy import PrefilterPolicy
from rule_prefilter import RulePreFilter

policy = PrefilterPolicy(
    prefilter=RulePreFilter(),
    downstream_policy=FullEscalatePolicy(),
)
```

The escalation policy above is a fallback for integration.
It can be replaced with Member 4's semantic approval policy.

The prefilter returns `None` when it cannot decide.
This means internal deferral, not human escalation.
Only the approval gate consumes the human attention budget.

## Full-Approve Baseline

The existing `FullApprovePolicy` in `approval_gate.py` supplies
the full-approve baseline. It must run independently of the
prefilter and downstream policy.

## Validation

```bash
python -m pytest test_tool_metadata.py test_rule_prefilter.py test_prefilter_policy.py -v
```

The current validation includes 17 rule cases, two integration
scenarios, and two metadata checks: 21 tests in total.

Metadata is verified against AgentDojo 0.1.35 Workspace implementations.
In particular, `get_unread_emails` changes email read flags and is
therefore not classified as read-only.

## Initial Reference Coverage

Run the offline diagnostic with:

```bash
python evaluate_reference_coverage.py
```

The report is saved to `member3_reference_coverage.json`.

Using AgentDojo 0.1.35 and the default prefilter configuration,
with no blocked tools or preapproved file permissions:

| Suite | Reference Calls | Directly Handled | Coverage |
|---|---:|---:|---:|
| Banking | 33 | 0 | 0.00% |
| Slack | 98 | 0 | 0.00% |
| Travel | 124 | 0 | 0.00% |
| Workspace | 84 | 2 | 2.38% |
| Total | 339 | 2 | 0.59% |

The two directly handled calls used `get_current_day`.
The remaining 337 calls were deferred.

These results describe offline reference-call fixtures without
tool execution or conversation history. They do not measure
live-agent coverage, safety accuracy, or TCR.

The initial rules have limited coverage. Further work should
expand supported tools while preserving authorization checks.
Local timing measurements are included in the JSON report.

## Remaining Work

- Connect the adapter to the shared experiment runner.
- Agree on the benchmark suites and trusted permission configuration.
- Measure coverage, deferral rate, and latency on actual agent trajectories.
- Evaluate false approvals and false denials using labeled evaluation data.
- Compare downstream policy calls with and without the prefilter.
- Complete joint testing with the semantic policy and simulated reviewer.
