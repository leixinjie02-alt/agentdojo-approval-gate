# Verified against AgentDojo 0.1.35 Workspace implementations.
# Resource scope describes modeled resources, not actual network activity.
# Destructive operations include deletion and cancellation.


def _metadata(
    read_only: bool,
    resource_scope: str = "remote",
    destructive: bool = False,
):
    return {
        "read_only": read_only,
        "resource_scope": resource_scope,
        "destructive": destructive,
    }


TOOL_METADATA = {
    # Email tools
    "send_email": _metadata(False),
    "delete_email": _metadata(False, destructive=True),

    # Retrieving unread emails also marks them as read.
    "get_unread_emails": _metadata(False),

    "get_sent_emails": _metadata(True),
    "get_received_emails": _metadata(True),
    "get_draft_emails": _metadata(True),
    "search_emails": _metadata(True),
    "search_contacts_by_name": _metadata(True),
    "search_contacts_by_email": _metadata(True),

    # Calendar tools
    "get_current_day": _metadata(True, resource_scope="local"),
    "search_calendar_events": _metadata(True),
    "get_day_calendar_events": _metadata(True),
    "create_calendar_event": _metadata(False),
    "cancel_calendar_event": _metadata(False, destructive=True),
    "reschedule_calendar_event": _metadata(False),
    "add_calendar_event_participants": _metadata(False),

    # Cloud drive tools
    "append_to_file": _metadata(False),
    "search_files_by_filename": _metadata(True),
    "create_file": _metadata(False),
    "delete_file": _metadata(False, destructive=True),
    "get_file_by_id": _metadata(True),
    "list_files": _metadata(True),
    "share_file": _metadata(False),
    "search_files": _metadata(True),
}