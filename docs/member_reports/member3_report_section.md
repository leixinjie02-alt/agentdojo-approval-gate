# Rule Based Prefiltering and the Full Approve Baseline

## Design and Scope

The rule-based pre-filter provides the first stage of the approval policy. It resolves narrowly defined cases before invoking a language model, using deterministic checks on trusted configuration, tool metadata, and the original user request. Rule evaluation incurs no model API cost. Its purpose is to avoid unnecessary semantic assessments while preserving further review for unresolved calls. The implementation consists of `RulePreFilter` in `src/gate/rule_prefilter.py` and the `PrefilterPolicy` adapter in `src/gate/prefilter_policy.py` [1, 2].

The rules deliberately require explicit matching conditions. Read-only status is insufficient to establish authorization, and a failed match triggers further assessment rather than automatic approval. The Full-approve baseline provides a separate comparison in which every proposed tool call receives approval.

## Tool Metadata

The metadata registry covers all 24 tools in the AgentDojo 0.1.35 Workspace suite. Each entry records `read_only`, `resource_scope`, and `destructive` [3]. The read-only flag determines eligibility for the implemented approval rules. Resource scope and destructive-operation annotations document tool behavior, but do not independently trigger approval or denial in the current filter.

The labels reflect modeled resources rather than actual network activity. For example, cloud-drive tools have remote resource scope within AgentDojo's simulated environment. Inspection also established that `get_unread_emails` marks returned messages as read, so it is classified as state-changing. This behavior is checked by an automated test.

Tools such as `get_received_emails` and `search_emails` have read-only metadata, but no automatic approval rule currently covers them. They continue to the downstream policy.

## Rule Evaluation

`RulePreFilter.evaluate(ctx)` returns a `RuleResult` containing a decision, rule identifier, and explanation. The decision is `APPROVE`, `DENY`, or `None`, where `None` means that no rule resolved the call. Table 1 summarizes evaluation order and conditions [1, 4].

**Table 1. Implemented rules in evaluation order**

| Rule | Required condition | Result |
|---|---|---|
| Explicit tool restriction | The tool appears in the trusted `blocked_tools` configuration. This check overrides approval rules. | Deny |
| Current date | The tool is `get_current_day`, its metadata is read-only, and no arguments are supplied. | Approve |
| Calendar query | The tool is `get_day_calendar_events`, metadata is read-only, and its only argument is a string-valued `day` matching a supported explicit calendar request. | Approve |
| File read | The tool is `get_file_by_id`, metadata is read-only, and its only argument is a string-valued `file_id` authorized for the original task. | Approve |
| No matching rule | No preceding condition resolves the call, including unknown tools or unsupported arguments. | Defer |

The calendar helper uses a full-request pattern and validates dates, including leap years. It recognizes supported queries with an ISO date or an English month name. For example, a request for appointments on 2024-05-15 can authorize a matching date query. A different date, an invalid date, or an unsupported request remains unresolved. Relative dates such as "today" are outside this parser's supported patterns.

File permissions come from `approved_file_ids_by_task`, a trusted mapping keyed by the original user request. Permission to read one file does not authorize another file, sharing, or deletion. The default configuration contains neither blocked tools nor preapproved file permissions. These settings must come from trusted configuration rather than injected tool content or benchmark labels.

## Policy Routing and Budget Control

`PrefilterPolicy.decide(ctx)` evaluates the rules first. A definite approval or denial returns immediately. Otherwise, the adapter calls the downstream policy and returns its decision [2]. In the combined strategy, the downstream component is the semantic LLM policy. A Full-escalate fallback can also be used for integration testing.

Internal deferral does not consume the human attention budget. Only a downstream `ESCALATE` decision that invokes the reviewer consumes one unit of budget. When the budget is exhausted, the gate blocks subsequent escalation requests. Rule-based approvals and denials require no reviewer call and leave the budget unchanged [5].

This separation gives the gateway a consistent three-way decision interface while allowing individual policy stages to leave a call unresolved. The rule result also retains an identifier and reason for inspection.

## Full Approve Baseline

The existing `FullApprovePolicy` in `src/gate/approval_gate.py`, supplied with the gateway implementation, returns `Decision.APPROVE` for every call [5]. It runs independently of the pre-filter and semantic policy so that it represents unguarded execution. Wrapping it with restrictive rules would change the baseline's meaning.

Full-approve performs no authorization screening. All proposed calls reach the tool executor, although a tool can still fail for ordinary execution reasons. The strategy invokes neither the policy LLM nor the reviewer, so its approval-policy and reviewer API costs are zero. Agent execution can still consume model tokens.

Its escalation count is zero by construction, and its approval behavior is independent of budget k. This does not establish a high safe task completion rate. A successful task may still include an unauthorized action, so completion and safety must be assessed separately. The baseline provides a reference for evaluating the utility, safety, and additional approval costs of guarded strategies. An offline regression test checks that Full-approve matches unguarded execution in the tested scenario.

## Validation and Results

### Offline functional tests

The pre-filter has 42 offline test cases across four test files [6]. Parameterized inputs count as separate cases. Tests use predefined inputs and scripted components rather than real LLM API calls.

**Table 2. Offline test coverage**

| Test area | Cases | Main checks |
|---|---:|---|
| Rule decisions | 27 | Approval boundaries, explicit restrictions, argument validation, task permissions, and deferral |
| Calendar parsing | 11 | Date formats, leap years, invalid dates, quoted or negative requests, and unsupported queries |
| Tool metadata | 2 | Workspace registry coverage and the unread-email state change |
| Gate integration | 2 | Routing and budget enforcement with reviewer approval and denial |
| Total | 42 | All cases passed |

The integration scenarios replay four tool calls with k = 1: an approved date query, a prohibited deletion, and two unresolved file reads. The first unresolved call reaches the reviewer. The final escalation is denied after budget exhaustion. Assertions check execution flags, remaining budget, downstream calls, and the absence of the blocked deletion's side effect. These tests establish behavior for the specified cases, rather than general security accuracy.

### Reference call coverage

The offline diagnostic evaluates reference calls from 97 tasks across four AgentDojo suites. It uses the default rule configuration, empty conversation histories, and no preapproved file permissions. Reference calls are not executed, and benchmark labels are not supplied to the policy. Coverage is the proportion of calls resolved by an approval or denial [7].

**Table 3. Offline reference call coverage**

| Suite | Reference calls | Resolved calls | Coverage |
|---|---:|---:|---:|
| Banking | 33 | 0 | 0.00% |
| Slack | 98 | 0 | 0.00% |
| Travel | 124 | 0 | 0.00% |
| Workspace | 84 | 3 | 3.57% |
| Total | 339 | 3 | 0.88% |

All three resolved calls were approvals. The remaining 336 calls were deferred. These results expose the filter's narrow default coverage, especially outside Workspace. They do not measure live-agent coverage, attack detection accuracy, or TCR@k.

### Early Workspace pilot

A separate early team pilot recorded 64 main-run tool calls across 14 attack variants of one Workspace user task, using the V3 semantic policy at k = 2. Rules directly approved seven calls, while 57 reached semantic assessment [8]. Thus, seven calls, or approximately 10.9% of this pilot's calls, bypassed the semantic model.

This pilot demonstrates a mechanism for avoiding some model assessments. It does not isolate the pre-filter's causal effect on task completion or human-review load. Live token usage and dollar costs were not recorded, so no numerical token or cost savings are claimed. Its call distribution also differs from the offline reference fixtures, preventing direct interpretation of the two percentages as a before-and-after improvement.

## Limitations and Further Work

The current filter relies on narrow request patterns and trusted configuration. It does not interpret full conversation history or resolve complex semantic attacks. Its metadata registry covers Workspace, while unmatched calls from other suites continue to the downstream policy.

Further development should add authorization checks for common queries, including email search, and expand metadata across suites. Each extension should include legitimate and adversarial cases to assess incorrect approvals as well as coverage. A matched comparison of the semantic policy with and without the pre-filter should measure model calls, token usage, latency, review load, and safe task completion under the same experimental settings. These measurements are needed to establish whether broader rules improve efficiency while preserving authorization boundaries.

## References

Repository revision: `2810fb5938410cda5d23b66c82a33a78aaa3fae3`.

[1] Rule implementation: [RulePreFilter](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/src/gate/rule_prefilter.py).

[2] Policy composition: [PrefilterPolicy](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/src/gate/prefilter_policy.py).

[3] Workspace tool registry: [TOOL_METADATA](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/src/utils/tool_metadata.py).

[4] Calendar request parser: [calendar_query_day](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/src/rules/calendar_rules.py).

[5] Gateway and baseline: [approval_gate.py](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/src/gate/approval_gate.py). Baseline regression: [test_gate.py](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/tests/test_gate.py).

[6] Member 3 tests: [Rule tests](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/tests/test_rule_prefilter.py), [Calendar tests](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/tests/test_calendar_rules.py), [Metadata tests](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/tests/test_tool_metadata.py), and [Integration tests](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/tests/test_prefilter_policy.py).

[7] Reference coverage: [Coverage results](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/data/results/member3_reference_coverage.json). Method: [Evaluation script](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/scripts/evaluate_reference_coverage.py).

[8] Early pilot: [Pilot summary](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/data/results/member4/summary.json). Scope and provenance: [Pilot documentation](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/2810fb5938410cda5d23b66c82a33a78aaa3fae3/data/results/member4/README.md).
