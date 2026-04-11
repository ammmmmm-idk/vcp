"""
VCP Logging Configuration
==========================
Centralized logging setup for all VCP components.

Features:
- Structured logging with named loggers
- File and console output
- Log rotation
- Component-based log names (vcp.chat, vcp.file, etc.)

Log format: timestamp level logger - message
"""
import logging


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    return logger
