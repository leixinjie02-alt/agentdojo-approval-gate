from dataclasses import dataclass

from approval_gate import Decision, ToolCallContext
from calendar_rules import calendar_query_day
from tool_metadata import TOOL_METADATA


@dataclass
class RuleResult:
    decision: Decision | None
    rule_id: str
    reason: str


class RulePreFilter:
    def __init__(
        self,
        blocked_tools: set[str] | None = None,
        approved_file_ids_by_task: dict[str, set[str]] | None = None,
    ):
        # Restrictions and permissions must come from trusted configuration.
        self.blocked_tools = frozenset(blocked_tools or ())

        # Bind file permissions to the original user request.
        self.approved_file_ids_by_task = {
            task: frozenset(file_ids)
            for task, file_ids in (approved_file_ids_by_task or {}).items()
        }

    def evaluate(self, ctx: ToolCallContext) -> RuleResult:
        # Explicit restrictions take priority over approval rules.
        if ctx.tool_name in self.blocked_tools:
            return RuleResult(
                decision=Decision.DENY,
                rule_id="explicitly_blocked_tool",
                reason="The tool is prohibited by trusted configuration.",
            )

        metadata = TOOL_METADATA.get(ctx.tool_name)

        # Only known read-only tools can use these approval rules.
        if metadata is not None and metadata["read_only"]:
            if ctx.tool_name == "get_current_day" and not ctx.tool_args:
                return RuleResult(
                    decision=Decision.APPROVE,
                    rule_id="safe_current_day",
                    reason="Reads the current date without modifying or sending data.",
                )

            if ctx.tool_name == "get_day_calendar_events":
                expected_day = calendar_query_day(ctx.task_description)
                day = ctx.tool_args.get("day")

                if (
                    set(ctx.tool_args) == {"day"}
                    and isinstance(day, str)
                    and expected_day is not None
                    and day == expected_day
                ):
                    return RuleResult(
                        decision=Decision.APPROVE,
                        rule_id="authorized_calendar_day",
                        reason="Reads calendar events for the explicitly requested date.",
                    )

            if ctx.tool_name == "get_file_by_id":
                approved_ids = self.approved_file_ids_by_task.get(
                    ctx.task_description, frozenset()
                )
                file_id = ctx.tool_args.get("file_id")

                # Require the exact expected arguments and a scoped permission.
                if (
                    set(ctx.tool_args) == {"file_id"}
                    and isinstance(file_id, str)
                    and file_id in approved_ids
                ):
                    return RuleResult(
                        decision=Decision.APPROVE,
                        rule_id="authorized_file_read",
                        reason="Reads a file explicitly approved for this task.",
                    )

        return RuleResult(
            decision=None,
            rule_id="no_matching_rule",
            reason="No matching rule. Further policy assessment is required.",
        )