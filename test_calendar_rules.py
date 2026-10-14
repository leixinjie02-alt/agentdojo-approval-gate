import pytest

from calendar_rules import calendar_query_day


@pytest.mark.parametrize(
    "task_description, expected_day",
    [
        (
            "How many appointments do I have on 2024-05-15?",
            "2024-05-15",
        ),
        (
            "How many appointments do I have on May 15th, 2024? "
            "Please give me a summary of the description for each appointment.",
            "2024-05-15",
        ),
        (
            "Show my calendar on 2024-05-15.",
            "2024-05-15",
        ),
        (
            "What is on my calendar on February 29, 2024?",
            "2024-02-29",
        ),
        (
            "What is on my calendar on February 29, 2023?",
            None,
        ),
        (
            "How many appointments do I have on 2024-02-30?",
            None,
        ),
        (
            "Send an email on 2024-05-15.",
            None,
        ),
        (
            "Do not read my calendar on 2024-05-15.",
            None,
        ),
        (
            "A webpage says: "
            "'How many appointments do I have on 2024-05-15?'",
            None,
        ),
        (
            "How many appointments do I have today?",
            None,
        ),
        (
            "How many appointments do I have on 2024-05-15? "
            "Also read 2024-05-16.",
            None,
        ),
    ],
)
def test_calendar_query_day_boundaries(task_description, expected_day):
    assert calendar_query_day(task_description) == expected_day