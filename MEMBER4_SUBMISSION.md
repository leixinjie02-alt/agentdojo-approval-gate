# Member 4 submission handoff — 14 October 2026

## Final choice

**V1 is the selected version for this submission.** The adapter, standalone assessor and `run_real.py` prompt default all use V1. V2 and V3 remain explicitly selectable. No prompt text was changed and no new model experiment was run.

Selection criterion: prefer the highest observed development exact-match count, good routing of ambiguity, fewer review requests than V3, and lower recorded token usage. V1 scored 11/12 with 3 escalations and 4,174 tokens. V2 scored 9/12 with 1 escalation and 4,539 tokens; V3 scored 9/12 with 7 escalations and 5,258 tokens. V1 correctly denied all four unsafe-labelled development cases, but incorrectly approved the ambiguous bulk-update case T12. This known weakness prevents a claim that V1 is uniformly safest. V2 would be preferable if avoiding all observed approvals of non-approval-labelled cases outweighed task utility and exact label agreement.

The separate V3 real pilot found 55 escalation requests out of 57 semantic calls, including all 42 read-only semantic calls. It motivates avoiding V3 as the default but is not a matched real-task comparison with V1/V2.

## Files to use

- `member4_report_section.md`: English report section with development comparison, V3 real pilot, decision rationale and limitations.
- `member1_integration_guide.md`: integration instructions and explicit V1 command for future team runs.
- `semantic_adapter.py`, `semantic_policy.py`, `prompts.py`: policy implementation and unchanged prompt variants.
- `run_real.py`: shared runner with V1 as the default semantic prompt; reviewer and budget logic are unchanged.
- `semantic_experiment_results.csv`, `test_dataset.py`: preserved development evidence.
- `data/member4/`: privacy-reduced pilot extracts, provenance and derived summary.
- `analyze_member4.py`: standard-library-only analysis; run `python analyze_member4.py` from the repository root.
- `test_adapter.py`, `test_integration.py`: offline regression and integration checks.

## What is complete

Member 4's implementation, three-prompt development comparison, existing-data version selection, real-pilot analysis and report/handoff are prepared for team integration. The recorded development CSV and original prompts have been preserved. Policy errors still escalate and the gate still enforces k.

## What these files do not establish

The available data do not establish V1's real AgentDojo TCR, real token usage/cost, or superiority over V2/V3. The V3 pilot is one Workspace user task with 14 attack variants, k=2 and one repetition per variant; its 11/14 safe completions are only a configuration-specific pilot TCR@2 if the team uses utility-success AND attack-failure as TCR. Prechecks are excluded. Zero attack successes are not a guarantee of safety. The reviewer is simulated.

The full team benchmark remains separate: matched task/attack/reviewer/model configurations across versions, no-attack runs, repeated trials, budgets and actual per-module usage accounting. `sweep_runner.py` uses simulated counts and unconditional success; do not report its output as measured benchmark performance. Missing live cost is null/unavailable, not zero. The assignment rubric and final submission destination were not provided; no claim of grading compliance or final submission is made.

## Verification

Recompute the analysis with `python analyze_member4.py`. Run offline tests with `python -m pytest test_adapter.py test_integration.py -q` in an environment containing AgentDojo 0.1.35, OpenAI 3.26.1 and pytest. Tests mock model responses; no paid model calls are needed. The regression checks verify that the selected default reaches model requests and runner policies, while preserving explicit V1/V2/V3 selection, safe fallback and budget enforcement.

Validation on 14 October 2026: **13 tests passed** (`test_adapter.py` and `test_integration.py`, 7.22 seconds), with one third-party deprecation warning. The analysis completed with all built-in consistency checks passing. No paid API calls were made.
