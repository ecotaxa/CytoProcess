import tempfile
import zipfile
from pathlib import Path

import click
import yaml

from cytoprocess import ecotaxa
from cytoprocess.logging import setup_logging, log_command_start, log_command_success
from cytoprocess.project import check_project_integrity, list_sample_assets
from cytoprocess.utils import format_file_size, raiseCytoError


def _create_batch_zip(zip_paths: list[Path], logger) -> Path:
    """Combine the contents of multiple zip files into a single zip in a temp directory.

    Several zip files are combined into a single zip file, where each original zip is added as a file at the root of the new zip.
    Returns the path to the combined zip.
    """
    batch_name = f"batch_{zip_paths[0].stem}_{zip_paths[-1].stem}"
    tmp_dir = Path(tempfile.mkdtemp())
    batch_zip_path = tmp_dir / f"{batch_name}.zip"
    logger.debug(f"Creating batch zip '{batch_zip_path.name}' from {len(zip_paths)} zip(s)")
    with zipfile.ZipFile(batch_zip_path, "w", zipfile.ZIP_STORED) as batch_zf:
        for zip_path in zip_paths:
            batch_zf.write(zip_path, zip_path.name)
    return batch_zip_path


def _extract_tsv_in_new_zip(zip_path: Path, logger) -> Path | None:
    """Extract the TSV from zip_path and re-zip it alone in a new temporary zip.

    The TSV is expected at the root of the zip as '{zip_path.stem}.tsv'.
    Returns the path to the new zip, or None if the TSV was not found.
    """
    # Extract the TSV file from the original zip, to a temporary directory
    tsv_name = f"ecotaxa_{zip_path.stem}.tsv"
    with zipfile.ZipFile(zip_path, "r") as zf:
        if tsv_name not in zf.namelist():
            raiseCytoError(f"  '{tsv_name}' not found in '{zip_path}', skipping", logger)
        tmp_dir = Path(tempfile.mkdtemp())
        zf.extract(tsv_name, path=tmp_dir)

    # Create a new zip with just that file
    new_zip_path = tmp_dir / zip_path.name
    with zipfile.ZipFile(new_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_dir / tsv_name, tsv_name)
    return new_zip_path


def run(ctx: click.Context, project: Path, username: str | None = None, password: str | None = None, update: bool = False, batch: int = 10):
    # Housekeeping for the command
    logger = setup_logging(command="upload", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Uploading samples to EcoTaxa", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    check_project_integrity(project, logger)

    # Load config from project
    logger.debug(f"Loading configuration from '{project / 'config' / 'config.yaml'}'")
    config_path =  project / "config" / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}
    
    # Get project_id from config
    ecotaxa_config = config.get("ecotaxa", {}) or {}
    project_id = ecotaxa_config.get("project_id")
    eco_url = ecotaxa_config.get("url", "https://ecotaxa.obs-vlfr.fr")
    api_url = f"{eco_url}/api"
    if not project_id:
        raiseCytoError(f"EcoTaxa project_id missing from '{config_path}'\nEdit the file to set 'ecotaxa: project_id'\nYou can find your EcoTaxa numeric project ID in the table at\n  {eco_url}/prj", logger)

    logger.debug(f"Creating output directory")
    ecotaxa_dir = project / "ecotaxa"
    ecotaxa_dir.mkdir(parents=True, exist_ok=True)
    
    # Authenticate
    token = ecotaxa.authenticate(api_url, username=username, password=password, logger=logger)
    if token is None:
        raiseCytoError("Authentication failed, cannot proceed with upload", logger)
    
    # Find zip files to upload
    zip_files = list_sample_assets(project, kind="zip",
                                   logger=logger, samples_mask=ctx.obj["sample"])
    if not zip_files:
        # list_sample_assets already logs a warning if no files are found, so we just stop here
        raiseCytoError(f"Stopping", logger)
    
    logger.info(f"Found {len(zip_files)} zip file(s) to upload")
    batch = max(1, batch)
    logger.info(f"Uploading in batches of {batch}")

    # Get and display project name
    project_info = ecotaxa.get_project_info(api_url, project_id, token, logger)
    if project_info:
        project_name = project_info.get("title", "Unknown")
    else:
        project_name = "Unknown"
        logger.warning("Could not retrieve project information")
    logger.info(f"Uploading to EcoTaxa project '{project_name}' [{project_id}]")
    
    # Get existing samples in the project
    existing_samples = ecotaxa.get_project_samples(api_url, project_id, token, logger)
    logger.debug(f"Found {len(existing_samples)} existing sample(s) in project")
    
    # Process zip files in batches: aggregate, upload, import, and monitor until complete
    batches = [zip_files[i:i + batch] for i in range(0, len(zip_files), batch)]
    for batch_zip_paths in batches:
        sample_ids = [z.stem.replace("ecotaxa_", "") for z in batch_zip_paths]
        batch_label = sample_ids[0] if len(sample_ids) == 1 else f"{sample_ids[0]} … {sample_ids[-1]} ({len(sample_ids)} samples)"
        logger.info(f"Batch: {batch_label}")

        # Skip the samples that already exist (unless updating)
        if not update:
            new_zip_paths = [z for z, sid in zip(batch_zip_paths, sample_ids) if sid not in existing_samples]
            skipped = len(batch_zip_paths) - len(new_zip_paths)
            if skipped:
                logger.info(f"  Skipping {skipped} sample(s) that already exist on EcoTaxa")
            if not new_zip_paths:
                continue
            batch_zip_paths = new_zip_paths
            sample_ids = [z.stem.replace("ecotaxa_", "") for z in batch_zip_paths]

        # Prepare the zip to upload:
        # - update mode: extract only TSVs from each zip and combine them
        # - normal mode: combine all zip contents into one zip
        if len(batch_zip_paths) == 1 and not update:
            # Single file – no aggregation needed
            zip_path = batch_zip_paths[0]
        elif update:
            # Combine TSV-only zips for the update
            tsv_zips = [_extract_tsv_in_new_zip(z, logger) for z in batch_zip_paths]
            tsv_zips = [z for z in tsv_zips if z is not None]
            if not tsv_zips:
                logger.warning("  No TSV files found in batch, skipping")
                continue
            zip_path = _create_batch_zip(tsv_zips, logger) if len(tsv_zips) > 1 else tsv_zips[0]
        else:
            zip_path = _create_batch_zip(batch_zip_paths, logger)

        # Upload via TUS (resumable, with live progress)
        logger.info(f"  Uploading '{zip_path.name}' (" + ("metadata only; " if update else "") + f"{format_file_size(zip_path.stat().st_size)})...")
        upload_result = ecotaxa.upload_file_tus(api_url, token, zip_path, logger=logger)
        logger.debug(f"Upload result: {upload_result}")
        
        if upload_result.get("errors"):
            for error in upload_result["errors"]:
                logger.error(f"  Error: {error}")
            continue
        
        server_path = upload_result.get("server_path")
        if not server_path:
            logger.warning(f"  No server path returned, upload may have failed")
            continue
        
        logger.debug(f"Uploaded to server path: '{server_path}'")
        logger.info(f"  ✔︎ Upload completed")
        
        # Import
        logger.debug(f"Importing batch: {sample_ids}")
        server_directory = Path(server_path).stem
        import_result = ecotaxa.import_file(api_url, project_id, token, server_directory,
                                            update_mode="Yes" if update else "", logger=logger)
        logger.debug(f"Import result: {import_result}")
        
        if import_result.get("errors"):
            for error in import_result["errors"]:
                logger.error(f"  Error: {error}")
            continue
        
        job_id = import_result.get("job_id", 0)
        if job_id <= 0:
            logger.warning("No job ID returned, import may have failed")
            continue
        
        logger.info(f"  Import started (job ID: {job_id}), monitoring progress...")
        
        # Monitor job until completion
        success = ecotaxa.monitor_job(api_url, job_id, token, logger=logger)
        if success:
            logger.info(f"  ✔︎ Import completed")
        else:
            logger.warning(f"  ✗ Import failed or requires manual intervention")

    logger.info(f"Your data is at {eco_url}/prj/{project_id}")
    log_command_success(logger, "Upload")
