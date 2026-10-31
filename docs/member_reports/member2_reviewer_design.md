# Member 2 — Full-Escalation Baseline and Simulated Human Reviewer

**Author:** Zhang Yushuang  
**Group:** A1  
**Course:** PE6203 — Generative AI & Agentic AI  
**Project:** Safety Approval Policies for Agent Harnesses (AgentDojo)  
**Primary implementation:** `src/adapters/simulated_reviewer.py`

## 1. Scope and Design Rationale

Member 2 was responsible for implementing and refining the **LLM-simulated human reviewer** used in the team's approval system and supporting its use in the **full-escalation baseline**. The reviewer determines whether a proposed agent tool call is reasonably authorized by the original user request. It is invoked only when the approval gate escalates a call and sufficient review budget remains.

This component addresses a central trade-off in agent safety. Approving an unauthorized operation can permit harmful actions induced by prompt injection, while denying a legitimate operation can prevent the agent from completing an authorized task. In particular, preparatory read-only operations may be necessary even when the user has not explicitly named the tool. The reviewer's objective is therefore not simply to reject suspicious-looking calls, but to distinguish **task-relevant, authorized actions** from **unnecessary, out-of-scope, or attacker-induced actions**.

The reviewer is distinct from both the shared **ApprovalGate** (Member 1), which intercepts calls and enforces the budget, and the **semantic approval policy** (Member 4), which can automatically approve, deny, or escalate. The simulated reviewer makes a binary **approve/deny** judgment after escalation.

## 2. Full-Escalation Baseline

The full-escalation baseline uses `FullEscalatePolicy`, which returns `ESCALATE` for every proposed tool call. The team's gate applies the per-task escalation budget *k* before requesting a simulated review:

1. **Budget available:** one review is consumed; the proposed call is sent to `SimulatedReviewer`.
2. **Reviewer approves:** the gate executes the call. **Reviewer denies:** the gate blocks the call.
3. **Budget exhausted:** the gate denies subsequent escalated calls without invoking the reviewer.

The budget is consumed by an escalation regardless of whether the reviewer ultimately approves or denies. Thus, full escalation is useful as a reference configuration for measuring review demand and the effect of a finite *k*, but it does not represent unlimited human oversight. Once *k* is exhausted, even a legitimate read or update can be blocked. Compared with the layered rule-based and semantic policies, this baseline highlights the potential cost of sending every call to review rather than reserving reviews for uncertain or consequential actions.

The gate, budget controller, and `FullEscalatePolicy` are shared team components. Member 2's implementation is the **reviewer used by the baseline**, not the gate or budget controller itself.

## 3. Simulated Reviewer Implementation

The reviewer is implemented as the `SimulatedReviewer` class in `src/adapters/simulated_reviewer.py`, exposing the interface `review(ctx) -> bool`. It uses **GPT-4o-mini** (default model identifier `gpt-4o-mini-2024-07-18`) through an OpenAI-compatible API client; the repository also supports OpenRouter through the `OPENROUTER_API_KEY` environment variable.

For each proposed tool call, the reviewer receives a structured request containing the following context:

| Input | Purpose |
|---|---|
| Original user task | Establishes the authorized objective and scope. |
| Tool name and description | Identifies the operation being proposed. |
| Tool arguments | Exposes material details, such as recipients, amounts, or target records. |
| Step index and recent conversation history | Provides relevant context about preceding user, assistant, and tool interactions. |

The implementation includes up to **12 recent messages** from the user, assistant, and tools, with bounded text fields to limit prompt size. It calls the model with `temperature=0` and requests a JSON object with a `decision` (`approve` or `deny`) and a short `reason`. A valid approval returns `True`; a denial returns `False`. Invalid decision values, malformed responses, and API exceptions produce **denial by default**, so a reviewer failure cannot silently become authorization.

To support auditability and cost accounting, the reviewer exposes `last_reason` and `last_usage` (prompt, completion, and total tokens). These fields are reset before each review to prevent stale diagnostic information from being attributed to a later call. The shared gate records the resulting decision and associated metadata in its experiment logs.

## 4. Authorization Prompt and Safety Refinement

The principal design work was refining the system prompt so that the reviewer judges each proposed action against the **original user's authorization**, rather than merely accepting whatever instructions appear in the agent's context. The revision was submitted as **GitHub Pull Request #3** and subsequently merged into `main`.

### 4.1 Defining the prompt-injection trust boundary

The revised prompt explicitly distinguishes the original user request from **lower-trust material**, including retrieved files, web pages, transaction descriptions, and tool outputs. Such material can provide task data, but cannot independently authorize new actions. For example, instructions embedded in a retrieved notice to change an account password or transfer funds must not be interpreted as a new request from the user.

This distinction is particularly important for **state-changing and external operations**. Changes to passwords, payment recipients, amounts, beneficiaries, account details, or external destinations require support from the user's original request and trustworthy context. A broad instruction to read a document does not, by itself, authorize unrelated security changes or financial transfers. The reviewer is instructed to deny high-impact actions when that authorization is missing or when material changes originate only from untrusted content.

### 4.2 Avoiding unnecessary denial of read-only calls

The team's earlier Banking failure analysis identified extensive blocking of read-only calls, including `get_balance`, `get_iban`, `get_user_info`, `get_most_recent_transactions`, and `get_scheduled_transactions`. These observations informed a more explicit rule: **relevant preparatory or verification reads may be authorized even if the user does not name each tool**. For example, inspecting existing transactions may be a reasonable step in carrying out an authorized refund or rent adjustment.

However, **read-only does not mean automatically safe**. The prompt continues to reject irrelevant or excessive access, access to another person's data without authorization, and reads used as steps toward unauthorized disclosure. This avoids replacing blanket overblocking with blanket approval.

Importantly, earlier blocking cannot be attributed solely to reviewer misjudgment: in a finite-budget baseline, calls can also be denied **without any reviewer invocation** after *k* is exhausted. Prompt refinement can improve the reviewer decisions that actually occur, but reducing budget-driven denials also requires more selective escalation upstream.

### 4.3 Reliability safeguards

Alongside the prompt changes, the revision clears per-call diagnostic state and explicitly rejects response values outside the expected `approve`/`deny` set. These changes strengthen interface reliability and log integrity. They are engineering safeguards, not independent proof of greater attack resistance.

## 5. Integration and Verification

The reviewer is instantiated by `make_reviewer()` in `scripts/run_real.py` and connects to the gate through its `review(ctx)` interface. Under full escalation, every call reaching an available review slot is assessed by the simulated reviewer. Under the layered policy, the rule pre-filter and semantic policy can resolve calls first; only their **escalation** decisions require the reviewer and consume *k*.

The repository includes **offline integration tests** in `tests/test_integration.py` that replace the model with controlled OpenAI-compatible fake responses. These tests exercise the reviewer interface within the real gate pipeline, review-budget enforcement, the separation between automated decisions and escalations, and logging of reviewer reasons and token usage. They also check that benchmark oracle information is not passed to the reviewer. Because model outputs are mocked, these tests support claims about **integration and control flow**, not claims about the live model's accuracy on attacks.

The team's earlier live Banking traces and failure cases provided useful diagnostic examples of excessive blocking and prompt-injection risks. Following the merge of PR #3, the repository moved the earlier-prompt run into `data/results/archive/`. Consequently, **those historical results must not be presented as performance measurements of the revised reviewer**, and they do not establish a before-and-after improvement. A matched live evaluation of the revised prompt, with consistent tasks and budgets, is still required to quantify its effect. Team-wide experimental results, TCR@k curves, and cost comparisons are addressed separately by the group members responsible for experiments and analysis.

## 6. Limitations and Future Work

An LLM-based simulated reviewer makes repeated benchmark evaluations practical without requiring a human to inspect every call. Nevertheless, it remains an **approximation of human authorization judgment**: it can misinterpret ambiguous requests, be influenced by misleading context, reject necessary steps, or approve an attacker-induced action. `temperature=0` and structured output improve consistency of the evaluation procedure but do not guarantee identical or correct decisions.

The full-escalation baseline also introduces review latency and token cost for each consulted call. More importantly, it spends a limited budget on both low-risk and high-risk cases, so legitimate tasks may fail after budget exhaustion. Improving the reviewer alone cannot resolve this system-level allocation problem.

Future work should evaluate the **merged reviewer** on held-out AgentDojo tasks using multiple budget values, compare it against its earlier version under matched conditions, and examine authorized and unauthorized calls separately. Useful measures include unauthorized approvals, legitimate-call denials, review demand, task completion, latency, and reviewer token cost. Attack success at the whole-task level should not be treated as a substitute for call-level authorization accuracy. More robust task-scoped permission evidence, adversarial tests involving retrieved content, and more selective escalation of clearly authorized low-risk calls would further strengthen the design.

## Implementation and Evidence References

- **Reviewer code:** [`src/adapters/simulated_reviewer.py`](https://github.com/leixinjie02-alt/agentdojo-approval-gate/blob/main/src/adapters/simulated_reviewer.py).
- **Gateway and budget interface:** `src/gate/approval_gate.py` (Member 1).
- **Benchmark integration:** `scripts/run_real.py`.
- **Offline integration tests:** `tests/test_integration.py`.
- **Prior failure examples:** `data/results/analysis/case_studies.md` (Member 6); historical reviewer-prompt runs in `data/results/archive/`.
- **Merged implementation change:** [Pull Request #3 — Improve M2 simulated reviewer prompt and safety checks](https://github.com/leixinjie02-alt/agentdojo-approval-gate/pull/3).
