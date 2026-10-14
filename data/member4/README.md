# Member 4 pilot evidence

The source is Member 1's supplied `m4_live_run_data.zip`; its SHA-256 and extraction method are in `provenance.json`. The source README is retained as `source_README.md` for configuration context and historical claims. Interpret raw README assertions through the audit in the report; not every causal attribution was independently verified.

`v3_live_gate.csv` retains all 64 main-run gate rows after excluding 112 prechecks. Tool arguments and full messages were omitted. `decided_by` and `read_only` are copied from the supplied summary and reflect its metadata. `v3_live_runs.csv` retains all 14 trace-level results and tool-call counts, with no injected text or contact addresses. Timestamps are retained as recorded; the source does not specify their timezone. `security=True` means attack succeeded, consistent with the source README and original summary CSV. No benchmark-version value was present in the traces.

`summary.json` is derived, not a second experiment. Regenerate it with:

```bash
python analyze_member4.py > data/member4/summary.json
```

The analyzer validates development row uniqueness, recorded correctness and token sums, run/call keys, trace call counts, budget transitions and execution outcomes. The source ZIP remains with the user; the repository provides reduced extracts and a hash for linking back to it. Missing live tokens/cost are null, not estimated from development data. The 14 attacked runs all use one user task, V3, k=2 and run_id=0. They are not repeated trials or a V1/V2/V3 benchmark.
