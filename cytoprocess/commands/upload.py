import tempfile
import zipfile
from pathlib import Path
import click
import yaml
from cytoprocess import ecotaxa
from cytoprocess.logging import setup_logging, log_command_start, log_command_success
from cytoprocess.project import check_project_integrity, list_sample_assets
from cytoprocess.utils import raiseCytoError, format_file_size


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


def run(ctx: click.Context, project: Path, username: str | None = None, password: str | None = None, update: bool = False):
    # Housekeeping for the command
    logger = setup_logging(command="upload", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Uploading samples to EcoTaxa", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    check_project_integrity(project, logger)

    # Load config from project
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
    
    # Process each zip file: upload, import, and monitor until complete
    for zip_path in zip_files:
        # Extract sample ID from filename (ecotaxa_<sample_id>.zip)
        sample_id = zip_path.stem.replace("ecotaxa_", "")
        logger.info(f"'{sample_id}'")

        # Skip if sample already exists (unless updating)
        if (sample_id in existing_samples) and not update:
            logger.info(f"  Skipping, sample already exists on EcoTaxa")
            continue

        # If we only update, we need to extract the TSV and re-zip it
        # because the API expects a zip file but we only want to upload the updated TSV
        if update:
            zip_path = _extract_tsv_in_new_zip(zip_path, logger)
        
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
        logger.debug(f"Importing {sample_id}")
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
