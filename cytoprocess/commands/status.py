import logging
from pathlib import Path

import click
import pandas as pd
import pyarrow.parquet as pq
import yaml

from cytoprocess import ecotaxa
from cytoprocess.logging import setup_logging, log_command_start, log_command_success
from cytoprocess.project import list_samples, path_to_sample_asset
from cytoprocess.utils import raiseCytoError


def _count_rows(parquet_file: Path, logger: logging.Logger) -> int | None:
    """
    Quickly count rows in a parquet file
    
    Args:
        parquet_file: Path to the parquet file
        logger: Logger instance for logging operations
    
    Returns:
        int: Number of rows in the parquet file, 0 if the file doesn't exist
        None: If an error occurs while reading the file
    """
    if not parquet_file.exists():
        return None
    try:
        pf = pq.ParquetFile(parquet_file)
        return pf.metadata.num_rows 
    except Exception as exc:
        logger.warning(f"Error occurred while reading '{parquet_file}': {exc}")
        return None


def _compute_sample_status(project: Path, sample_id: str, meta_df: pd.DataFrame, ecotaxa_samples: list, logger: logging.Logger) -> dict:
    """Build per-sample status using the same file requirements as _ensure_complete_samples."""

    # raw
    cyz_file = project / path_to_sample_asset(sample_id, "cyz", logger)

    # global metadata
    this_sample_meta = meta_df[meta_df["sample_id"] == sample_id]
    sample_in_meta = this_sample_meta.shape[0] > 0
    this_sample_meta = this_sample_meta.drop(columns=["sample_id"])
    sample_meta_filled = sample_in_meta and not this_sample_meta.isnull().all(axis=1).iloc[0]

    # converted
    json_file = project / path_to_sample_asset(sample_id, "json", logger)

    # instrument metadata
    metadata_file = project / path_to_sample_asset(sample_id, "metadata", logger)

    # cytometric summary features
    cytometric_features_file = project / path_to_sample_asset(sample_id, "cytometric_features", logger)
    cytometric_features_count = _count_rows(cytometric_features_file, logger)

    # pulses
    pulses_summaries_file = project / path_to_sample_asset(sample_id, "pulses_summaries", logger)
    pulses_summaries_count = _count_rows(pulses_summaries_file, logger)
    pulses_plots_dir = project / path_to_sample_asset(sample_id, "pulses_plots", logger)
    pulses_plots_count = len(list(pulses_plots_dir.glob("*.png"))) if pulses_plots_dir.exists() else 0
   
    # images
    images_dir = project / path_to_sample_asset(sample_id, "images", logger)
    images_count = len(list(images_dir.glob("*.jpg"))) if images_dir.exists() else 0
    masks_count = len(list(images_dir.glob("*.gif"))) if images_dir.exists() else 0
    image_features_file = project / path_to_sample_asset(sample_id, "image_features", logger)
    image_features_count = _count_rows(image_features_file, logger)

    # ecotaxa files
    ecotaxa_file = project / path_to_sample_asset(sample_id, "zip", logger)

    # ecotaxa uploads
    sample_on_ecotaxa = sample_id in ecotaxa_samples

    status = {
        "sample_id": sample_id,

        "cyz_present": cyz_file.exists(),
        
        "sample_in_meta": sample_in_meta,
        "sample_meta_filled": sample_meta_filled,
        
        "json_present": json_file.exists(),
        
        "instrument_data_present": metadata_file.exists(),
        
        "cytometric_features_present": cytometric_features_count is not None,
        "cytometric_features_count": cytometric_features_count,
        
        "pulses_summaries_present": pulses_summaries_count is not None,
        "pulses_summaries_count": pulses_summaries_count,
        "pulses_plots_present": pulses_plots_dir.exists(),
        "pulses_plots_count": pulses_plots_count,
        
        "images_present": images_dir.exists(),
        "images_count": images_count,
        "masks_count": masks_count,
        "image_features_present": image_features_count is not None,
        "image_features_count": image_features_count,

        "ecotaxa_file_present": ecotaxa_file.exists(),

        "sample_on_ecotaxa": sample_on_ecotaxa,
    }

    return status


def _define_sample_progress(sample_status: dict) -> tuple[str, str]:
    """Create a compact progress string and infer the next command to run."""

    STATUS_STEPS = [
        ("copy .cyz", lambda s: s["cyz_present"]),
        ("list", lambda s: s["sample_meta_filled"]),
        ("convert", lambda s: s["json_present"]),
        ("extract_meta", lambda s: s["instrument_data_present"]),
        ("extract_cyto", lambda s: s["cytometric_features_present"]),
        ("summarise_pulses", lambda s: s["pulses_summaries_present"] and s["pulses_plots_present"]),
        ("extract_images",
         lambda s: s["images_present"] and s["image_features_present"],
        ),
        ("prepare", lambda s: s["ecotaxa_file_present"]),
        ("upload", lambda s: s["sample_on_ecotaxa"]),
    ]
    # TODO do something with the counts

    # Define a progress indicator
    green = "\x1b[32m"
    red = "\x1b[31m"
    reset = "\x1b[0m"
    step_ok = [check(sample_status) for _, check in STATUS_STEPS]
    progress = "".join(f"{green}✔︎{reset}" if ok else f"{red}✗{reset}" for ok in step_ok)
    
    # Define which is the next command
    for (command, _), ok in zip(STATUS_STEPS, step_ok):
        if not ok:
            return progress, command

    return progress, None


def _format_sample_id(sample_id: str, width: int = 30) -> str:
    """Format sample id for display, truncating long values with ellipsis."""
    if len(sample_id) > width:
        sample_id = sample_id[: width - 1] + "…"
    display_sample_id = f"{sample_id:>{width}}"
    return display_sample_id


def run(ctx: click.Context, project: Path, width: int = 40):
    # Housekeeping for the command
    logger = setup_logging(command="status", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Computing processing status", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))

    # List all samples, everywhere
    samples = list_samples(project, logger, samples_mask=ctx.obj["sample"])
    logger.info(f"{len(samples)} sample(s) found")


    # Read the global metadata file
    meta_file = project / "meta" / "samples.csv"
    try:
        meta_df = pd.read_csv(meta_file)
    except Exception as exc:
        logger.warning(f"Could not read '{meta_file}' to determine which samples are listed: {exc}")


    # Get samples on EcoTaxa
    config_path =  project / "config" / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}
    ecotaxa_config = config.get("ecotaxa", {}) or {}
    project_id = ecotaxa_config.get("project_id")
    api_url = ecotaxa_config.get("url", "https://ecotaxa.obs-vlfr.fr") + "/api"
    
    if not project_id:
        ecotaxa_samples = []
        logger.warning(f"No EcoTaxa project ID found in config file '{config_path}', skipping EcoTaxa status checks")
    else:
        token = ecotaxa.authenticate(api_url, logger=logger)
        if token is None:
            raiseCytoError("Authentication failed, cannot check EcoTaxa status", logger)
        else:
            ecotaxa_samples = ecotaxa.get_project_samples(api_url, project_id, token, logger)
            logger.debug(f"Found {len(ecotaxa_samples)} sample(s) in EcoTaxa project '{project_id}'")

    # Compute status for each sample
    statuses = [
        _compute_sample_status(project, sample_id, meta_df, ecotaxa_samples, logger)
        for sample_id in samples
    ]

    # Display it in a compact form
    display_sample_ids = [_format_sample_id(s["sample_id"], width=width) for s in statuses]
    for status, display_sample_id in zip(statuses, display_sample_ids):
        progress, next_command = _define_sample_progress(status)
        print(f"{display_sample_id} {progress} " + (f"→ {next_command}" if next_command else ""))
    print("")
    print(f"Status indicators are for the presence of (1) cyz file, (2) row in meta/samples.csv, (3) converted json file, (4) instrument metadata, (5) cytometric features, (6) pulse summaries, (7) images, (8) zip file for EcoTaxa, and (9) sample on EcoTaxa. For each sample, the next step to run is indicated on the right (or None if the sample is fully processed).")

    log_command_success(logger, "Status")
