"""Utility functions for cytoprocess."""

import logging
import math
from pathlib import Path

import click
import ijson
import yaml


def get_json_section(json_file: Path, key: str, logger: logging.Logger) -> dict | list | None:
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


def load_config(project: Path, logger: logging.Logger) -> dict:
    """
    Load the configuration from the project's config.yaml file.
    
    Args:
        project: The project directory path
        logger: The logger instance to use for logging
        
    Returns:
        The configuration as a dictionary, or an empty dict if not found.
        
    Examples:
        >>> logger = logging.getLogger("cytoprocess.example")
        >>> config = load_config(Path('/path/to/project'), logger)
    """

    config_file = project / "config" / "config.yaml"
    
    if not config_file.exists():
        raiseCytoError(f"Configuration file not found: '{config_file}', run 'cytoprocess create {project}' again.", logger)
    
    logger.info(f"Read metadata fields list from '{config_file}'")
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    return config


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


def imshow(img):
    """Utility function to display an image (for debugging)."""
    import matplotlib.pyplot as plt
    plt.imshow(img, cmap='gray', vmin=0, vmax=255)
    plt.axis('off')
    plt.show()
