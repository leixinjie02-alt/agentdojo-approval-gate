from agentdojo.default_suites.v1.tools.email_client import get_unread_emails
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite import get_suite

from tool_metadata import TOOL_METADATA


def test_metadata_covers_workspace_tools():
    suite = get_suite("v1.2", "workspace")
    runtime = FunctionsRuntime(suite.tools)

    assert set(TOOL_METADATA) == set(runtime.functions)


def test_unread_email_metadata_matches_actual_behavior():
    suite = get_suite("v1.2", "workspace")
    env = suite.load_and_inject_default_environment({})

    before = {
        email_id: email.read
        for email_id, email in env.inbox.emails.items()
    }

    get_unread_emails(env.inbox)

    after = {
        email_id: email.read
        for email_id, email in env.inbox.emails.items()
    }

    # Verify that the fixture actually exercises a state change.
    assert before != after

    # The metadata must agree with the observed read-flag mutation.
    assert TOOL_METADATA["get_unread_emails"]["read_only"] == (
        before == after
    )