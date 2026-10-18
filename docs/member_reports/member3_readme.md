> **Repository layout note (2026-10-18):** files were reorganised by function. Code is in `src/`, tests in `tests/`, runnable scripts in `scripts/`, results in `data/results/`. Renamed: `analyze_member4.py` → `scripts/analyze_results.py`, `member1_integration_guide.md` → `docs/integration_guide.md`, `MEMBER4_SUBMISSION.md` → `docs/member_reports/member4_submission.md`, `data/member4/` → `data/results/member4/`. Run tests from the repository root with `python -m pytest -q`. See the root `README.md`.

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
- `calendar_rules.py`: Recognizes supported explicit calendar queries.
- `test_calendar_rules.py`: Date parsing and request boundary tests.

## Implemented Rules

1. Deny tools explicitly blocked by trusted configuration.
2. Approve `get_current_day` when no arguments are supplied.
3. Approve `get_file_by_id` only when:
   - The metadata identifies it as a read-only tool.
   - The arguments contain exactly one string-valued `file_id`.
   - That file ID is approved for the original user request.
4. Approve `get_day_calendar_events` only when:
   - The original request matches a supported explicit calendar query.
   - The arguments contain exactly one string-valued `day`.
   - The supplied day matches the date in the original request.
5. Defer all other calls to the downstream policy.

Complex calendar requests and relative dates remain deferred.

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
python -m pytest tests/test_calendar_rules.py tests/test_tool_metadata.py tests/test_rule_prefilter.py tests/test_prefilter_policy.py -v
```

The current validation includes 27 rule cases, 11 calendar-parser
cases, two integration scenarios, and two metadata checks:
42 tests in total.

Metadata is verified against AgentDojo 0.1.35 Workspace implementations.
In particular, `get_unread_emails` changes email read flags and is
therefore not classified as read-only.

## Initial Reference Coverage

## Reference Coverage

Run the offline diagnostic with:

```bash
python scripts/evaluate_reference_coverage.py
```

The current report is saved to `data/results/member3_reference_coverage.json`.

Both versions use AgentDojo 0.1.35 with no blocked tools or
preapproved file permissions.

| Suite | Reference Calls | Initial Coverage | Current Coverage |
|---|---:|---:|---:|
| Banking | 33 | 0.00% | 0.00% |
| Slack | 98 | 0.00% | 0.00% |
| Travel | 124 | 0.00% | 0.00% |
| Workspace | 84 | 2.38% | 3.57% |
| Total | 339 | 0.59% | 0.88% |

The initial version directly handled two calls.
The current version directly handles three calls and defers 336.
The additional handled call uses the scoped calendar-day rule.

These results describe offline reference-call fixtures without
tool execution or conversation history. They do not measure
live-agent coverage, safety accuracy, or TCR.

Coverage remains limited. Local diagnostic timing measurements
are included in the JSON report.

## Remaining Work

- Connect the adapter to the shared experiment runner.
- Agree on the benchmark suites and trusted permission configuration.
- Measure coverage, deferral rate, and latency on actual agent trajectories.
- Evaluate false approvals and false denials using labeled evaluation data.
- Compare downstream policy calls with and without the prefilter.
- Complete joint testing with the semantic policy and simulated reviewer.
