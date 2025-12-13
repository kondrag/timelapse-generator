"""Logging configuration for the timelapse generator."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from ..config.settings import settings


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[Path] = None,
    max_file_size: Optional[int] = None,
    backup_count: Optional[int] = None
) -> logging.Logger:
    """Set up logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file
        max_file_size: Maximum log file size in bytes
        backup_count: Number of backup log files to keep

    Returns:
        Configured logger instance
    """
    # Use settings if not provided
    if level is None:
        level = settings.logging.level
    if log_file is None:
        log_file = settings.logging.file_path
    if max_file_size is None:
        max_file_size = settings.logging.max_file_size
    if backup_count is None:
        backup_count = settings.logging.backup_count

    # Get the root logger
    logger = logging.getLogger("timelapse_generator")
    logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if log file is specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(f"timelapse_generator.{name}")


# Initialize logging when module is imported
if not logging.getLogger("timelapse_generator").handlers:
    setup_logging()