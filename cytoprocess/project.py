"""Project/sample path and discovery helpers for cytoprocess."""

import logging
from pathlib import Path

import click
import pandas as pd

from cytoprocess.utils import raiseCytoError


def check_project_integrity(project: Path, logger: logging.Logger) -> bool:
    """
    Check if the project directory has the expected structure and files.

    Args:
        project: The project directory path
        logger: The logger instance to use for logging
    Returns:
        True if the project structure looks correct, False otherwise.
    """
    expected_dirs = ["raw", "meta", "config"]
    for d in expected_dirs:
        if not (project / d).exists():
            raiseCytoError(f"Expected directory '{d}' is missing in '{project}'", logger)
            return False

    config_file = project / "config" / "config.yaml"
    if not config_file.exists():
        raiseCytoError(f"Configuration file '{config_file}' does not exist", logger)
        return False

    logger.debug(f"Project '{project}' passed integrity check")
    return True
# TODO use this in other commands that access the project structure, to fail early with a clear error message if the structure is not correct


def path_to_sample_asset(sample: str, kind: str, logger: logging.Logger) -> Path:
    """
    Generate the expected path for an asset (file, directory) of a given kind.

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
        return f"raw/{sample}.cyz"
    elif kind == "json" or kind == "converted":
        return f"work/{sample}/converted_data.json"
    elif kind == "images" or kind == "pulses_plots":
        return f"work/{sample}/{kind}"
    elif kind == "metadata" or kind == "pulses_summaries" or kind == "image_features" or kind == "cytometric_features":
        return f"work/{sample}/{kind}.parquet"
    elif kind == "zip" or kind == "tsv":
        return f"ecotaxa/{sample}.{kind}"
    else:
        raiseCytoError(f"Invalid kind '{kind}'", logger)


def list_sample_assets(project: Path, kind: str, logger: logging.Logger, ctx: click.Context = None) -> list:
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
    # Determine command to run when no asset is present, depending on kind
    if kind == "cyz":
        command = "create"
    elif kind == "json":
        command = "convert"
    elif kind == "zip" or kind == "tsv":
        command = "prepare"
    # NB: There may be other kinds here, the same as in path_to_sample_asset,
    #     but for now we only use this function for cyz and json files
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
        logger.warning(f"Metadata file '{meta_file}' does not exist, run `cytoprocess list '{project}'` to create it")
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
    Collect known sample IDs from raw, work, and meta.

    Args:
        project: The project directory path
        sample_filter: Optional sample name to filter by
        logger: The logger instance to use for logging

    Returns:
        A sorted list of unique sample IDs found in the project,
        optionally filtered by sample_filter.
    """

    # Check that the project structure looks correct before trying to list samples, to avoid confusing errors later on
    check_project_integrity(project, logger)

    sample_ids: set[str] = set()

    # in raw
    sample_ids.update([f.stem for f in list_sample_assets(project, "cyz", logger)])

    # in meta/samples.csv
    sample_ids.update(list_samples_in_meta_file(project, logger))

    # in work
    work_dir = project / "work"
    if work_dir.exists():
        sample_ids.update([d.name for d in work_dir.iterdir() if d.is_dir()])

    samples = sorted(sample_ids)
    if not samples:
        logger.warning("No samples found in raw/, work/, and meta/samples.csv")

    logger.debug(f"Found {len(samples)} sample(s)")

    # Filter by sample_filter if provided
    if sample_filter:
        return [sample_filter]

    return samples
