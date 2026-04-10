"""
Protocol message validation using JSON schemas.
Validates all incoming message types and formats.
"""
from typing import Any, Dict, Tuple


# Define expected schemas for each action type
MESSAGE_SCHEMAS = {
    "auth": {
        "required": ["action", "email", "session_token"],
        "optional": ["auxiliary"],
        "types": {
            "action": str,
            "email": str,
            "session_token": str,
            "auxiliary": bool,
        }
    },
    "create_group": {
        "required": ["action", "group_name"],
        "optional": [],
        "types": {
            "action": str,
            "group_name": str,
        }
    },
    "chat": {
        "required": ["action", "message_id", "color"],
        "optional": ["sender", "msg", "encrypted", "nonce", "ciphertext"],
        "types": {
            "action": str,
            "message_id": str,
            "sender": str,
            "msg": str,
            "color": str,
            "encrypted": bool,
            "nonce": str,
            "ciphertext": str,
        }
    },
    "assistant_chat": {
        "required": ["action", "group_id", "message_id", "msg"],
        "optional": ["color"],
        "types": {
            "action": str,
            "group_id": str,
            "message_id": str,
            "msg": str,
            "color": str,
        }
    },
    "file": {
        "required": ["action", "filename"],
        "optional": ["sender", "message_id", "timestamp", "filesize", "group_id"],
        "types": {
            "action": str,
            "filename": str,
            "sender": str,
            "message_id": str,
            "timestamp": str,
            "filesize": int,
            "group_id": str,
        }
    },
    "leave_group": {
        "required": ["action", "group_id"],
        "optional": [],
        "types": {
            "action": str,
            "group_id": str,
        }
    },
    "signup": {
        "required": ["action", "fullname", "email", "password"],
        "optional": [],
        "types": {
            "action": str,
            "fullname": str,
            "email": str,
            "password": str,
        }
    },
    "login": {
        "required": ["action", "email", "password"],
        "optional": [],
        "types": {
            "action": str,
            "email": str,
            "password": str,
        }
    },
    "verify_auth_code": {
        "required": ["action", "email", "code"],
        "optional": [],
        "types": {
            "action": str,
            "email": str,
            "code": str,
        }
    },
    "ping": {
        "required": ["action"],
        "optional": [],
        "types": {
            "action": str,
        }
    },
    "join": {
        "required": ["action", "group_id"],
        "optional": ["group_name", "username"],
        "types": {
            "action": str,
            "group_id": str,
            "group_name": str,
            "username": str,
        }
    },
    "join_group": {
        "required": ["action", "group_id"],
        "optional": [],
        "types": {
            "action": str,
            "group_id": str,
        }
    },
    "rename": {
        "required": ["action", "new_name"],
        "optional": [],
        "types": {
            "action": str,
            "new_name": str,
        }
    },
}


def validate_message_schema(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validates a protocol message against its schema.
    Returns (is_valid, error_message).
    """
    if not isinstance(payload, dict):
        return False, "Payload must be a dictionary"

    action = payload.get("action")
    if not action:
        return False, "Missing required field: action"

    if not isinstance(action, str):
        return False, "Field 'action' must be a string"

    # Check if action has a defined schema
    if action not in MESSAGE_SCHEMAS:
        # Allow unknown actions to pass through - they might be handled elsewhere
        return True, ""

    schema = MESSAGE_SCHEMAS[action]

    # Check required fields
    for field in schema["required"]:
        if field not in payload:
            return False, f"Missing required field: {field}"

    # Check field types
    for field, value in payload.items():
        if field in schema["types"]:
            expected_type = schema["types"][field]
            if not isinstance(value, expected_type):
                return False, f"Field '{field}' must be of type {expected_type.__name__}"

    # Don't reject unexpected fields - allow for forward compatibility
    # This makes the validator less strict and prevents breaking changes

    return True, ""
