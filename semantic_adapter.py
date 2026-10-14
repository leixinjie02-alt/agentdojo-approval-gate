"""Member 4 policy compatible with Member 1's ApprovalGate."""
import json
from approval_gate import Decision, ToolCallContext
from semantic_policy import semantic_risk_assessment
from prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_V2, SYSTEM_PROMPT_V3

PROMPTS = {"V1": SYSTEM_PROMPT, "V2": SYSTEM_PROMPT_V2, "V3": SYSTEM_PROMPT_V3}


class SemanticPolicy:
    def __init__(self, prompt_version="V3", assessor=None):
        if prompt_version not in PROMPTS:
            raise ValueError("prompt_version must be V1, V2 or V3")
        self.prompt_version = prompt_version
        self.assessor = assessor or semantic_risk_assessment

    def decide(self, ctx: ToolCallContext) -> Decision:
        try:
            result = self.assessor(
                user_task=ctx.task_description,
                tool_name=ctx.tool_name,
                tool_parameters=ctx.tool_args,
                agent_history=[json.dumps(message, ensure_ascii=False, default=str)
                               for message in ctx.messages],
                tool_description=ctx.tool_description,
                prompt=PROMPTS[self.prompt_version],
            )
            return {"auto_approve": Decision.APPROVE,
                    "auto_deny": Decision.DENY,
                    "escalate": Decision.ESCALATE}.get(result, Decision.ESCALATE)
        except Exception:
            # Failed assessments never authorize execution.
            return Decision.ESCALATE
