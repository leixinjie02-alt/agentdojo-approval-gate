import pytest

from approval_gate import Decision, ToolCallContext
from rule_prefilter import RulePreFilter


def make_context(tool_name, tool_args=None):
    return ToolCallContext(
        tool_name=tool_name,
        tool_args={} if tool_args is None else tool_args,
        tool_description="Test tool",
        task_description="Check my calendar for today.",
        messages=[],
        step_index=0,
        budget_remaining=2,
    )


def test_approve_current_day():
    context = make_context("get_current_day")

    result = RulePreFilter().evaluate(context)

    assert result.decision == Decision.APPROVE


@pytest.mark.parametrize(
    "tool_name, tool_args",
    [
        ("send_email", {"recipients": ["person@example.com"]}),
        ("delete_file", {"file_id": "file_1"}),
        ("share_file", {"file_id": "file_1"}),
        ("unknown_tool", {}),
    ],
)
def test_defer_calls_without_matching_rule(tool_name, tool_args):
    context = make_context(tool_name, tool_args)

    result = RulePreFilter().evaluate(context)

    assert result.decision is None


def test_defer_current_day_with_unexpected_arguments():
    context = make_context(
        "get_current_day",
        {"unexpected_argument": "value"},
    )

    result = RulePreFilter().evaluate(context)

    assert result.decision is None

def test_deny_explicitly_blocked_tool():
    context = make_context("delete_file", {"file_id": "file_1"})
    prefilter = RulePreFilter(blocked_tools={"delete_file"})

    result = prefilter.evaluate(context)

    assert result.decision == Decision.DENY


def test_explicit_restriction_overrides_approval_rule():
    context = make_context("get_current_day")
    prefilter = RulePreFilter(blocked_tools={"get_current_day"})

    result = prefilter.evaluate(context)

    assert result.decision == Decision.DENY
@pytest.mark.parametrize(
    "tool_name, tool_args, task_description, expected",
    [
        (
            "get_file_by_id",
            {"file_id": "file_1"},
            "Read file_1.",
            Decision.APPROVE,
        ),
        (
            "get_file_by_id",
            {"file_id": "file_2"},
            "Read file_1.",
            None,
        ),
        (
            "get_file_by_id",
            {},
            "Read file_1.",
            None,
        ),
        (
            "get_file_by_id",
            {"file_id": ["file_1"]},
            "Read file_1.",
            None,
        ),
        (
            "get_file_by_id",
            {"file_id": "file_1", "extra": "value"},
            "Read file_1.",
            None,
        ),
        (
            "get_file_by_id",
            {"file_id": "file_1"},
            "Check my calendar.",
            None,
        ),
        (
            "share_file",
            {"file_id": "file_1"},
            "Read file_1.",
            None,
        ),
        (
            "delete_file",
            {"file_id": "file_1"},
            "Read file_1.",
            None,
        ),
    ],
)
def test_task_scoped_file_permission(
    tool_name, tool_args, task_description, expected
):
    context = make_context(tool_name, tool_args)
    context.task_description = task_description

    prefilter = RulePreFilter(
        approved_file_ids_by_task={"Read file_1.": {"file_1"}}
    )

    result = prefilter.evaluate(context)

    assert result.decision == expected


def test_defer_file_read_without_trusted_permission():
    context = make_context("get_file_by_id", {"file_id": "file_1"})
    context.task_description = "Read file_1."

    result = RulePreFilter().evaluate(context)

    assert result.decision is None

CALENDAR_TASK = "How many appointments do I have on 2024-05-15?"


@pytest.mark.parametrize(
    "tool_name, tool_args, task_description, expected",
    [
        (
            "get_day_calendar_events",
            {"day": "2024-05-15"},
            CALENDAR_TASK,
            Decision.APPROVE,
        ),
        (
            "get_day_calendar_events",
            {"day": "2024-05-15"},
            "Show my calendar on May 15th, 2024.",
            Decision.APPROVE,
        ),
        (
            "get_day_calendar_events",
            {"day": "2024-05-16"},
            CALENDAR_TASK,
            None,
        ),
        (
            "get_day_calendar_events",
            {},
            CALENDAR_TASK,
            None,
        ),
        (
            "get_day_calendar_events",
            {"day": ["2024-05-15"]},
            CALENDAR_TASK,
            None,
        ),
        (
            "get_day_calendar_events",
            {"day": "2024-05-15", "extra": "value"},
            CALENDAR_TASK,
            None,
        ),
        (
            "get_day_calendar_events",
            {"day": "2024-05-15"},
            "Send an email on 2024-05-15.",
            None,
        ),
        (
            "get_day_calendar_events",
            {"day": "2024-05-15"},
            "Do not read my calendar on 2024-05-15.",
            None,
        ),
        (
            "create_calendar_event",
            {
                "title": "New event",
                "start_time": "2024-05-15 10:00",
                "end_time": "2024-05-15 11:00",
            },
            CALENDAR_TASK,
            None,
        ),
    ],
)
def test_calendar_query_permission(
    tool_name, tool_args, task_description, expected
):
    context = make_context(tool_name, tool_args)
    context.task_description = task_description

    result = RulePreFilter().evaluate(context)

    assert result.decision == expected


def test_blocked_calendar_tool_overrides_query_permission():
    context = make_context(
        "get_day_calendar_events",
        {"day": "2024-05-15"},
    )
    context.task_description = CALENDAR_TASK
    prefilter = RulePreFilter(
        blocked_tools={"get_day_calendar_events"}
    )

    result = prefilter.evaluate(context)

    assert result.decision == Decision.DENY