"""Utility functions for cytoprocess."""

import logging
import click
import ijson
from pathlib import Path
from datetime import datetime
import copy
import re
import math


def setup_logging(command: str = None, project: str = None, debug: bool = False) -> logging.Logger:
    """
    Set up logging for a command, with optional file and console handlers.
    
    Args:
        command: The command name (e.g., 'convert', 'cleanup')
        project: The project directory path. If provided, logs are also written to file.
        debug: If True, console logs at DEBUG level; otherwise INFO level.
        
    Returns:
        A configured logger instance for the command.
        
    Examples:
        >>> logger = setup_logging('convert', '/path/to/project', debug=True)
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
        # get ANSI color codes
        yellow = "\x1b[33m"
        red = "\x1b[31m"
        bold_red = "\x1b[1;31m"
        reset = "\x1b[0m"
        format = '%(message)s'

        FORMATS = {
            logging.DEBUG: format,
            logging.INFO: format,
            logging.WARNING: yellow + format + reset,
            logging.ERROR: red + format + reset,
            logging.CRITICAL: bold_red + format + reset
        }

        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)
    # Use the colour formatter (only for console output)
    console_handler.setFormatter(ColourFormatter())
    logger.addHandler(console_handler)
    
    # File handler (only if project is specified)
    if project is not None and Path(project).exists():
        # Define a custom file handler that cleans log messages
        class CleanupFormatter:
            def emit(self, record):
                s = record.getMessage()
                # Remove newlines
                s = s.replace("\n", " ")
                # Remove ANSI color codes
                s = re.sub(r'\x1b\[[0-9;]*m', '', s)
                # Remove Emojis
                s = re.sub(r'[^\x00-\x7F]+', '>', s)
                rec = copy.copy(record)
                rec.msg = s
                super().emit(rec)
        class CleanFileHandler(CleanupFormatter, logging.FileHandler):
            pass
        
        # Ensure logs directory exists
        log_dir = Path(project) / "logs"
        ensure_project_dir(project, "logs")
        log_filename = f"{datetime.now().strftime('%Y-%m-%d')}_cytoprocess.log"
        
        file_handler = CleanFileHandler(log_dir / log_filename, mode='a')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)-7s\t%(name)-16s\t%(message)s'))
        logger.addHandler(file_handler)
    
    return logger


def log_command_start(logger: logging.Logger, message: str, project: str):
    """
    Log the start of a command execution with fancy formatting.
    
    Args:
        logger: The logger instance to use
        message: The message to log
        project: The project directory path
        
    Examples:
        >>> logger = logging.getLogger("cytoprocess.example")
        >>> log_command_start(logger, 'convert', '/path/to/project')
    """
    start = "\x1b[1;34m" # bold blue
    reset = "\x1b[0m"
    logger.info(f"\n{start}🛠️ {message} " + (f"in project '{Path(project).stem}'" if project else "") + f"{reset}")


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
    start = "\x1b[0;32m" # non bold green
    reset = "\x1b[0m"
    logger.info(f"{start}✅ {command} operation successful{reset}")


def ensure_project_dir(project: str, subdir: str) -> Path:
    """
    Ensure a subdirectory exists within a project directory.
    
    Creates the directory and any parent directories if they don't exist.
    
    Args:
        project: The project directory path
        subdir: The subdirectory name (e.g., "config", "meta", "converted")
        
    Returns:
        Path object for the created/verified directory
        
    Examples:
        >>> config_dir = ensure_project_dir('/path/to/project', 'config')
        >>> meta_dir = ensure_project_dir('/path/to/project', 'meta')
    """
    target_dir = Path(project) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def get_json_section(json_file: Path, key: str, logger: logging.Logger):
    """
    Load a specific section from a JSON file using streaming.
    
    Args:
        json_file: Path to the JSON file
        key: The top-level key to extract (e.g., 'instrument', 'particles', 'images')
        
    Returns:
        The section as a dict/list, or None if not found.
        
    Examples:
        >>> logger = logging.getLogger("cytoprocess.example")
        >>> instrument = get_json_section(Path('data.json'), 'instrument', logger)
        >>> images = get_json_section(Path('data.json'), 'images', logger)
    """
    logger.debug(f"Reading '{key}' section from {json_file.name}")

    with open(json_file, 'rb') as f:
        # Use ijson to stream only the specified part
        parser = ijson.items(f, key, use_float=True)
        data = next(parser, None)
        
        if data is None:
            logger.warning(f"No '{key}' key found in '{json_file.name}'")
        
    return data


def path_to_sample_asset(sample: str, kind: str, logger: logging.Logger) -> Path:
    """
    Generate the expected file name for a sample of a given kind.
    
    Args:
        sample: The sample name (without extension)
        kind: The type of file/directory
        logger: The logger instance to use for logging
        
    Returns:
        The expected file name as a Path object.
        
    Examples:
        >>> path_to_sample_asset('my_sample', 'json', logger)
        >>> path_to_sample_asset('my_sample', 'cyz', logger)
        >>> path_to_sample_asset('my_sample', 'zip', logger)
    """

    if kind == "cyz" or kind == "raw":
        return  f"raw/{sample}.cyz"
    elif kind == "json" or kind == "converted":
        return f"work/{sample}/converted_data.json"
    elif kind == "images" or kind == "pulses_plots":
        return f"work/{sample}/{kind}"
    elif kind == "pulses" or kind == "image_features" or kind == "cytometric_features":
        return f"work/{sample}/{kind}.parquet"
    elif kind == "zip" or kind == "ecotaxa":
        return f"ecotaxa/{sample}.zip"
    else:
        raiseCytoError(f"Invalid kind '{kind}'", logger)
    

def list_sample_assets(project: str, kind: str, logger: logging.Logger, ctx=None) -> list:
    """
    List all expected asset files for a given sample.
    
    Args:
        project: The project directory path
        sample: The sample name (without extension)
        kind: The type of file/directory to retrieve
        logger: The logger instance to use for logging
        ctx: The Click context object, used to get the sample name when called from a command with a --sample option
    
    Returns:
        A list of Path objects for the expected files/directories    
    """
    # Determine directory and extension based on kind
    if kind == "cyz":
        command= "create"
    else:
        raiseCytoError(f"Invalid kind '{kind}'", logger)
    
    project = Path(project)
    sample = getattr(ctx, "obj", {}).get("sample")
    if sample:
        asset = project / path_to_sample_asset(sample, kind, logger)
        if not asset.exists():
            logger.warning(f"No {kind} file found for sample '{sample}'\nRun `cytoprocess --sample '{sample}' {command} '{project}'`")
            return []
        logger.debug(f"Found {kind} file for sample '{sample}': '{asset}'")
        return [asset]
    else:
        assets = sorted(list(project.glob(path_to_sample_asset("*", kind, logger))))
        if len(assets) == 0:
            logger.warning(f"No {kind} files found in '{project}'\nRun `cytoprocess {command} '{project}'`")
            return []
        logger.debug(f"Found {len(assets)} {kind} files in '{project}'")
        return assets


def raiseCytoError(message: str, logger: logging.Logger = None):
    """
    Custom exception for cytoprocess errors.
    
    Args:
        message: The error message to display.
        logger: The logger instance to use for logging the error.
    
    Examples:
        >>> raiseCytoError("An error occurred")
    """
    # log the error if logger is provided
    # this allows to log this error in the file log as well
    # (which logs at DEBUG level)
    if logger:
        logger.debug(message)
    raise click.ClickException(click.style(message, fg="red"))


def format_file_size(size: int) -> str:
    """
    Format a file size in bytes into a human-readable string.
    
    Args:
        size: The size in bytes to format.
        
    Returns:
        A human-readable string representing the size (e.g., "10.5 MB").
        
    Examples:
        >>> format_size(1024)
        '1.0 KB'
        >>> format_size(1048576)
        '1.0 MB'
        >>> format_size(123456789)
        '117.7 MB'
    """
    if size == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB")
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f"{s} {size_name[i]}"
