"""Logging helpers for cytoprocess commands."""

import copy
import logging
import re
from datetime import datetime
from pathlib import Path


def setup_logging(command: str = None, project: Path = None, debug: bool = False) -> logging.Logger:
    """
    Set up logging for a command, with optional file and console handlers.

    Args:
        command: The command name (e.g., 'convert', 'cleanup')
        project: The project directory path. If provided, logs are also written to file.
        debug: If True, console logs at DEBUG level; otherwise INFO level.

    Returns:
        A configured logger instance for the command.

    Examples:
        >>> logger = setup_logging('convert', Path('/path/to/project'), debug=True)
        >>> logger = setup_logging('install')  # Console only
    """

    logger = logging.getLogger(f"{command}" if command else "cytoprocess")
    logger.setLevel(logging.DEBUG)  # Logger captures all; handlers filter

    # Prevent adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    # Default console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)

    # Output some messages in colour
    class ColourFormatter(logging.Formatter):
        yellow = "\x1b[33m"
        red = "\x1b[31m"
        bold_red = "\x1b[1;31m"
        reset = "\x1b[0m"
        format = "%(message)s"

        FORMATS = {
            logging.DEBUG: format,
            logging.INFO: format,
            logging.WARNING: yellow + format + reset,
            logging.ERROR: red + format + reset,
            logging.CRITICAL: bold_red + format + reset,
        }

        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)

    # Use the colour formatter (only for console output)
    console_handler.setFormatter(ColourFormatter())
    logger.addHandler(console_handler)

    # File handler (only if project is specified)
    if project is not None and project.exists():
        # Define a custom file handler that cleans log messages
        class CleanupFormatter:
            def emit(self, record):
                s = record.getMessage()
                # Remove newlines
                s = s.replace("\n", " ")
                # Remove ANSI color codes
                s = re.sub(r"\x1b\[[0-9;]*m", "", s)
                # Remove Emojis
                s = re.sub(r"[^\x00-\x7F]+", ">", s)
                rec = copy.copy(record)
                rec.msg = s
                super().emit(rec)

        class CleanFileHandler(CleanupFormatter, logging.FileHandler):
            pass

        # Ensure logs directory exists
        log_dir = project / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_filename = f"{datetime.now().strftime('%Y-%m-%d')}_cytoprocess.log"

        file_handler = CleanFileHandler(log_dir / log_filename, mode="a")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s\t%(levelname)-7s\t%(name)-16s\t%(message)s")
        )
        logger.addHandler(file_handler)

    return logger


def log_command_start(logger: logging.Logger, message: str, project: Path = None):
    """
    Log the start of a command execution with fancy formatting.

    Args:
        logger: The logger instance to use
        message: The message to log
        project: The project directory path

    Examples:
        >>> logger = logging.getLogger("cytoprocess.example")
        >>> log_command_start(logger, 'convert', Path('/path/to/project'))
    """
    start = "\x1b[1;34m"  # bold blue
    reset = "\x1b[0m"
    logger.info(
        f"\n{start}\U0001f6e0\ufe0f {message} "
        + (f"in project '{project.stem}'" if project else "")
        + f"{reset}"
    )


def log_command_success(logger: logging.Logger, command: str):
    """
    Log the successful completion of a command with fancy formatting.

    Args:
        logger: The logger instance to use
        command: The command name to log

    Examples:
        >>> logger = logging.getLogger("cytoprocess.example")
        >>> log_command_success(logger, 'convert')
    """
    start = "\x1b[0;32m"  # non bold green
    reset = "\x1b[0m"
    logger.info(f"{start}\u2705 {command} operation successful{reset}")
