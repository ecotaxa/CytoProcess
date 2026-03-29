"""Utility functions for cytoprocess."""

import logging
import click
import ijson
from pathlib import Path
import math
import yaml
import pandas as pd


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
    elif kind == "metadata" or kind == "pulses_summaries" or kind == "image_features" or kind == "cytometric_features":
        return f"work/{sample}/{kind}.parquet"
    elif kind == "zip" or kind == "ecotaxa":
        return f"ecotaxa/{sample}.zip"
    else:
        raiseCytoError(f"Invalid kind '{kind}'", logger)
    

def list_sample_assets(project: Path, kind: str, logger: logging.Logger, ctx: click.Context =None) -> list:
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
    elif kind == "json":
        command = "convert"
    else:
        raiseCytoError(f"Invalid kind '{kind}'", logger)
    
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


def list_samples_in_meta_file(project: Path, logger: logging.Logger) -> list[str]:
    """
    Extract sample IDs from meta/samples.csv if it exists.
    
    Args:
        project: The project directory path
        logger: The logger instance to use for logging

    Returns:
        A list of sample IDs found in column sample_id of project/meta/samples.csv.
    """
    meta_file = project / "meta" / "samples.csv"
    if not meta_file.exists():
        logger.warning(f"Metadata file '{meta_file}' does not exist")
        return list()

    try:
        meta_df = pd.read_csv(meta_file, usecols=["sample_id"])
        samples_in_meta = meta_df["sample_id"].dropna().astype(str).tolist()
        logger.debug(f"Found {len(samples_in_meta)} sample(s) in '{meta_file}'")
        return samples_in_meta
    except ValueError:
        raiseCytoError(f"Column 'sample_id' is missing in '{meta_file}'")
        return list()


def list_samples(project: Path, sample_filter: str | None, logger: logging.Logger) -> list[str]:
    """
    Collect known sample IDs from raw, work, and meta

    Args:
        project: The project directory path
        sample_filter: An optional sample name to filter by (if provided, only this sample will be returned)
        logger: The logger instance to use for logging
    
    Returns:
        A sorted list of unique sample IDs found in the project, optionally filtered by sample_filter.
    """

    # collect 
    sample_ids: set[str] = set()

    raw_dir = project / "raw"
    if raw_dir.exists():
        sample_ids.update([f.stem for f in list_sample_assets(project, "cyz", logger)])

    work_dir = project / "work"
    if work_dir.exists():
        sample_ids.update([d.name for d in work_dir.iterdir() if d.is_dir()])

    sample_ids.update(list_samples_in_meta_file(project, logger))

    samples = sorted(sample_ids)
    if not samples:
        logger.warning("No samples found in raw/, work/, or meta/samples.csv")

    logger.debug(f"Found {len(samples)} sample(s)")

    if sample_filter:
        logger.info(f"Checking status for sample: '{sample_filter}'")
        return [sample_filter]

    return samples



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
