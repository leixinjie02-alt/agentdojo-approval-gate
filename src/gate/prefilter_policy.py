from approval_gate import ApprovalPolicy, Decision, ToolCallContext
from rule_prefilter import RulePreFilter, RuleResult


class PrefilterPolicy:
    """Run deterministic rules before the downstream approval policy."""

    def __init__(
        self,
        prefilter: RulePreFilter,
        downstream_policy: ApprovalPolicy,
    ):
        self.prefilter = prefilter
        self.downstream_policy = downstream_policy
        self.last_rule_result: RuleResult | None = None

    def decide(self, ctx: ToolCallContext) -> Decision:
        result = self.prefilter.evaluate(ctx)
        self.last_rule_result = result

        if result.decision is not None:
            return result.decision

        return Decision(self.downstream_policy.decide(ctx))