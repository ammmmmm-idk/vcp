import os
import re

from config import MAX_FILENAME_LENGTH

INVALID_WINDOWS_CHARS = set('<>:"/\\|?*')
RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def validate_attachment_filename(filename: str) -> tuple[bool, str]:
    if not filename:
        return False, "File name is missing."

    if filename != os.path.basename(filename):
        return False, "File name must not include folders."

    if len(filename) > MAX_FILENAME_LENGTH:
        return False, f"File name is too long. Maximum length is {MAX_FILENAME_LENGTH} characters."

    if filename.endswith((" ", ".")):
        return False, "File name cannot end with a space or period."

    if any(char in INVALID_WINDOWS_CHARS for char in filename):
        return False, "File name contains invalid characters."

    if any(ord(char) < 32 for char in filename):
        return False, "File name contains control characters."

    stem = filename.split(".", 1)[0].upper()
    if stem in RESERVED_WINDOWS_NAMES:
        return False, "File name uses a reserved system name."

    if re.fullmatch(r"\.+", filename):
        return False, "File name is invalid."

    return True, ""
