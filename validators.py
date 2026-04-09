# Save as: validators.py
"""Input validation functions for VCP security"""
import re
from config import MAX_GROUP_NAME_LENGTH, MAX_MESSAGE_LENGTH

# Email validation regex (basic RFC 5322 compliant)
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Group name: alphanumeric, spaces, hyphens, underscores only
GROUP_NAME_REGEX = re.compile(r'^[a-zA-Z0-9 _-]+$')

# Dangerous AI prompt patterns (prevent prompt injection)
DANGEROUS_PROMPT_PATTERNS = [
    r'ignore\s+(previous|all)\s+instructions',
    r'system\s*:',
    r'<\s*script',
    r'javascript\s*:',
    r'on\w+\s*=',  # onclick=, onerror=, etc
]


def validate_email(email: str) -> tuple[bool, str]:
    """Validate email format"""
    if not email:
        return False, "Email is required"

    if len(email) > 254:  # RFC 5321
        return False, "Email is too long"

    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format"

    return True, ""


def validate_group_name(name: str) -> tuple[bool, str]:
    """Validate group name"""
    if not name:
        return False, "Group name is required"

    if len(name) < 3:
        return False, "Group name must be at least 3 characters"

    if len(name) > MAX_GROUP_NAME_LENGTH:
        return False, f"Group name too long (max {MAX_GROUP_NAME_LENGTH} characters)"

    if not GROUP_NAME_REGEX.match(name):
        return False, "Group name can only contain letters, numbers, spaces, hyphens, and underscores"

    # Prevent all-whitespace names
    if name.strip() == "":
        return False, "Group name cannot be only whitespace"

    return True, ""


def validate_message(message: str) -> tuple[bool, str]:
    """Validate chat message"""
    if not message:
        return False, "Message cannot be empty"

    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Message too long (max {MAX_MESSAGE_LENGTH} characters)"

    # Check for null bytes (can cause issues in some contexts)
    if '\x00' in message:
        return False, "Message contains invalid characters"

    return True, ""


def validate_username(username: str) -> tuple[bool, str]:
    """Validate username/display name"""
    if not username:
        return False, "Username is required"

    if len(username) < 2:
        return False, "Username must be at least 2 characters"

    if len(username) > 50:
        return False, "Username too long (max 50 characters)"

    # Prevent whitespace-only names
    if username.strip() == "":
        return False, "Username cannot be only whitespace"

    return True, ""


def sanitize_ai_prompt(prompt: str) -> tuple[bool, str]:
    """
    Check AI prompts for injection attempts
    Returns (is_safe, sanitized_prompt)
    """
    if not prompt:
        return True, prompt

    # Check for dangerous patterns
    for pattern in DANGEROUS_PROMPT_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return False, "Prompt contains potentially unsafe content"

    # Limit length
    if len(prompt) > 2000:
        return False, "Prompt too long (max 2000 characters)"

    return True, prompt.strip()


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password meets minimum security requirements"""
    if not password:
        return False, "Password is required"

    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if len(password) > 128:
        return False, "Password is too long (max 128 characters)"

    # Check for at least one uppercase letter
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    # Check for at least one lowercase letter
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    # Check for at least one digit
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"

    return True, ""
