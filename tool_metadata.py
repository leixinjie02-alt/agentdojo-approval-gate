# Trusted metadata for known AgentDojo Workspace tools.
# Resource scope describes the modeled resource, not actual network activity.

TOOL_METADATA = {
    "get_current_day": {
        "read_only": True,
        "resource_scope": "local",
        "destructive": False,
    },
    "get_file_by_id": {
        "read_only": True,
        "resource_scope": "remote",
        "destructive": False,
    },
    "send_email": {
        "read_only": False,
        "resource_scope": "remote",
        "destructive": False,
    },
    "share_file": {
        "read_only": False,
        "resource_scope": "remote",
        "destructive": False,
    },
    "delete_file": {
        "read_only": False,
        "resource_scope": "remote",
        "destructive": True,
    },
}