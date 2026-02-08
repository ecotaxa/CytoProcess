import logging
import getpass
from pathlib import Path
import time
import yaml
import keyring
import requests
from cytoprocess.utils import setup_logging, log_command_start, log_command_success, raiseCytoError, get_sample_files, format_file_size

# EcoTaxa API base URL
ECOTAXA_API_URL = "https://ecotaxa.obs-vlfr.fr/api"
KEYRING_SERVICE = "cytoprocess-ecotaxa"


def _get_stored_token(logger: logging.Logger) -> str | None:
    """Retrieve stored token from keyring."""
    try:
        return keyring.get_password(KEYRING_SERVICE, "token")
    except Exception as e:
        logger.debug(f"Could not retrieve token from keyring: {e}")
        return None


def _store_token(logger: logging.Logger, token: str) -> bool:
    """Store token in keyring."""
    try:
        keyring.set_password(KEYRING_SERVICE, "token", token)
        return True
    except Exception as e:
        logger.warning(f"Could not store token in keyring: {e}")
        return False


def _clear_token(logger: logging.Logger) -> None:
    """Clear stored token from keyring."""
    try:
        keyring.delete_password(KEYRING_SERVICE, "token")
    except Exception:
        pass


def _validate_token(logger: logging.Logger, token: str) -> bool:
    """Check if the token is still valid by calling /users/me."""
    try:
        response = requests.get(
            f"{ECOTAXA_API_URL}/users/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def _login(logger: logging.Logger, username: str, password: str) -> str | None:
    """
    Authenticate with EcoTaxa API and return JWT token.
    
    Returns None if authentication fails.
    """
    try:
        response = requests.post(
            f"{ECOTAXA_API_URL}/login",
            json={"username": username, "password": password},
            timeout=30,
        )
        if response.status_code == 200:
            # The API returns the token as a plain string (JSON string)
            return response.json()
        else:
            logger.error(f"Login failed: {response.text}")
            return None
    except requests.RequestException as e:
        logger.error(f"Login request failed: {e}")
        return None


def _get_user_info(logger: logging.Logger, token: str) -> dict | None:
    """Get current user information."""
    try:
        response = requests.get(
            f"{ECOTAXA_API_URL}/users/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        return None
    except requests.RequestException:
        return None


def _get_project_info(logger: logging.Logger, token: str, project_id: int) -> dict | None:
    """
    Get project information from EcoTaxa.
    
    Args:
        token: JWT authentication token
        project_id: EcoTaxa project ID
        
    Returns:
        Project information dict or None if request fails.
        Contains fields like 'title', 'projid', 'status', etc.
    """
    try:
        response = requests.get(
            f"{ECOTAXA_API_URL}/projects/{project_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            logger.error(f"Access denied to project {project_id}")
        elif response.status_code == 404:
            logger.error(f"Project {project_id} not found")
        return None
    except requests.RequestException as e:
        logger.error(f"Failed to get project info: {e}")
        return None


def _get_project_samples(logger: logging.Logger, token: str, project_id: int) -> set[str]:
    """
    Get the set of sample IDs that exist in an EcoTaxa project.
    
    Args:
        token: JWT authentication token
        project_id: EcoTaxa project ID
        
    Returns:
        Set of sample IDs (orig_id) in the project.
    """
    try:
        response = requests.get(
            f"{ECOTAXA_API_URL}/samples/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"project_ids": str(project_id), "id_pattern": "*"},
            timeout=60,
        )
        if response.status_code == 200:
            samples = response.json()
            # Extract sample orig_id from the response
            return {s.get("orig_id", "") for s in samples if s.get("orig_id")}
        else:
            logger.warning(f"Failed to get samples: {response.text}")
            return set()
    except requests.RequestException as e:
        logger.warning(f"Failed to get project samples: {e}")
        return set()


def authenticate(logger: logging.Logger, username: str | None = None, password: str | None = None) -> str | None:
    """
    Authenticate with EcoTaxa API.
    
    First tries to use a stored token. If not available or invalid,
    uses provided credentials or prompts the user.
    
    Args:
        username: Optional email address. If not provided, will prompt.
        password: Optional password. If not provided, will prompt.
        
    Returns:
        JWT token if authentication successful, None otherwise.
    """
    # Try stored token first
    token = _get_stored_token(logger)
    if token and _validate_token(logger, token):
        user_info = _get_user_info(logger, token)
        if user_info:
            logger.info(f"Authenticated as: {user_info.get('name', 'Unknown')} ({user_info.get('email', 'Unknown')})")
        return token
    elif token:
        logger.warning("Stored token is invalid, need to re-authenticate")
        _clear_token(logger)
    
    # Use provided credentials or prompt
    if not username:
        print("\nEcoTaxa Authentication Required")
        username = input("username (email): ").strip()
    if not username:
        raiseCytoError("EcoTaxa username is required", logger)
    
    if not password:
        password = getpass.getpass("password: ")
    if not password:
        raiseCytoError("EcoTaxa password is required", logger)
    
    # Attempt login
    token = _login(logger, username, password)
    if token is None:
        raiseCytoError("Authentication failed. Please check your EcoTaxa username and password.", logger)
    
    # Store the token
    if _store_token(logger, token):
        logger.info("Authentication token stored securely in system keyring")
    
    # Show user info
    user_info = _get_user_info(logger, token)
    if user_info:
        logger.info(f"Authenticated as: {user_info.get('name', 'Unknown')} ({user_info.get('email', 'Unknown')})")
    
    return token


def upload_file(logger: logging.Logger, token: str, zip_path: Path, timeout: int = 300) -> dict:
    """
    Upload a zip file to EcoTaxa user's file area.
    
    Args:
        token: JWT authentication token
        zip_path: Path to the zip file to upload
        timeout: Timeout in seconds for the upload request
        
    Returns:
        Dictionary with 'server_path' if successful, or 'errors' list if failed.
    """
    if not zip_path.exists():
        raiseCytoError(f"File not found: {zip_path}", logger)
    
    logger.debug(f"Uploading '{zip_path.name}'")
    
    try:
        # NB: upload is a synchronous operation now, not a job
        #     so we can only wait for the response
        with open(zip_path, "rb") as f:
            response = requests.post(
                f"{ECOTAXA_API_URL}/user_files/",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (zip_path.name, f, "application/zip")},
                timeout=timeout
            )
        
        if response.status_code != 200:
            raiseCytoError(f"File upload failed: {response.text}", logger)
        
        server_path = response.json()
        logger.debug(f"File uploaded to: {server_path}")
        return {"server_path": server_path}
        
    except requests.RequestException as e:
        raiseCytoError(f"File upload failed: {e}", logger)


def import_file(logger: logging.Logger, token: str, project_id: int, server_path: str) -> dict:
    """
    Start an import job for a file already uploaded to EcoTaxa.
    
    Args:
        token: JWT authentication token
        project_id: EcoTaxa project ID
        server_path: Path to the file on EcoTaxa server (from upload_file)
        
    Returns:
        Dictionary with 'job_id' if successful, or 'errors' list if failed.
    """
    logger.info(f"Starting import to project {project_id}...")
    
    import_req = {
        "source_path": server_path,
        "skip_loaded_files": False,
        "skip_existing_objects": False,
        "update_mode": "",
    }
    
    try:
        response = requests.post(
            f"{ECOTAXA_API_URL}/file_import/{project_id}",
            headers={"Authorization": f"Bearer {token}"},
            json=import_req,
            timeout=60,
        )
        
        # let the import job start
        time.sleep(2)

        if response.status_code == 200:
            result = response.json()
            if result.get("job_id", 0) > 0:
                logger.debug(f"Import job created: {result['job_id']}")
            return result
        else:
            raiseCytoError(f"Import failed: {response.text}", logger)
            
    except requests.RequestException as e:
        raiseCytoError(f"Import request failed: {e}", logger)


def get_job(logger: logging.Logger, token: str, job_id: int) -> dict | None:
    """
    Get job status from EcoTaxa API.
    
    Args:
        token: JWT authentication token
        job_id: Job ID to check
        
    Returns:
        Job information dict or None if request fails
    """
    try:
        response = requests.get(
            f"{ECOTAXA_API_URL}/jobs/{job_id}/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        return None
    except requests.RequestException:
        return None


def monitor_job(logger: logging.Logger, token: str, job_id: int, poll_interval: float = 2.0) -> bool:
    """
    Monitor a job until it completes.
    
    Args:
        token: JWT authentication token
        job_id: Job ID to monitor
        poll_interval: Seconds between status checks
        
    Returns:
        True if job completed successfully (state 'F'), False otherwise
    """    
    last_progress = -1
    while True:
        job_info = get_job(logger, token, job_id)
        if job_info is None:
            logger.error("Failed to get job status")
            return False
        
        state = job_info.get("state", "")
        progress = job_info.get("progress_pct", 0) or 0
        progress_msg = job_info.get("progress_msg", "")
        
        # Only print if progress changed
        if progress != last_progress:
            print(f"  Progress: {progress}% - {progress_msg}")
            last_progress = progress
        
        # Check terminal states
        # P: Pending, R: Running, A: Asking, E: Error, F: Finished
        if state == "F":
            logger.debug("Job completed successfully")
            return True
        elif state == "E":
            errors = job_info.get("errors", [])
            logger.error(f"Job failed with errors: {errors}")
            return False
        elif state == "A":
            # Job is asking for user input - we can't handle this
            logger.error("Job requires user input on EcoTaxa web interface")
            return False
        
        time.sleep(poll_interval)


def run(ctx, project, username: str | None = None, password: str | None = None):
    logger = setup_logging(command="upload", project=project, debug=ctx.obj["debug"])

    log_command_start(logger, "Uploading samples to EcoTaxa", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    project = Path(project)
    # TODO abstract cheching the existence of the prpoject and of some files in it in a function; have it raise a FileNotFound error and handle it with try:except in cli.py

    # Load config from project
    config_path =  project / "config" / "config.yaml"
    if not config_path.exists():
        raiseCytoError(f"Config file not found: '{config_path}', run 'cytoprocess create {project}' again.", logger)

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}
    
    # Get project_id from config
    ecotaxa_config = config.get("ecotaxa", {}) or {}
    project_id = ecotaxa_config.get("project_id")
    
    if not project_id:
        raiseCytoError(f"EcoTaxa project_id missing from '{config_path}'\nEdit the file to set 'ecotaxa: project_id'\nYou can find your EcoTaxa numeric project ID in the table at\n  https://ecotaxa.obs-vlfr.fr/prj", logger)

    ecotaxa_dir = project / "ecotaxa"

    # Authenticate
    token = authenticate(logger, username=username, password=password)
    if token is None:
        raiseCytoError("Authentication failed, cannot proceed with upload", logger)
    
    # Find zip files to upload
    zip_files = get_sample_files(project, logger, kind="zip", ctx=ctx)
    if not zip_files:
        raiseCytoError(f"No ecotaxa_*.zip files found in '{ecotaxa_dir}', run 'cytoprocess prepare_ecotaxa {project}' first.", logger)
    
    logger.info(f"Found {len(zip_files)} zip file(s) to upload")
    
    # Get and display project name
    project_info = _get_project_info(logger, token, project_id)
    if project_info:
        project_name = project_info.get("title", "Unknown")
    else:
        project_name = "Unknown"
        logger.warning("Could not retrieve project information")
    logger.info(f"Uploading to EcoTaxa project '{project_name}' [{project_id}]")
    
    # Get existing samples in the project
    existing_samples = _get_project_samples(logger, token, project_id)
    logger.debug(f"Found {len(existing_samples)} existing sample(s) in project")
    
    # Process each zip file: upload, import, and monitor until complete
    for zip_path in zip_files:
        # Extract sample ID from filename (ecotaxa_<sample_id>.zip)
        sample_id = zip_path.stem.replace("ecotaxa_", "")
        logger.info(f"'{sample_id}'")
        
        # Skip if sample already exists
        if sample_id in existing_samples:
            logger.info(f"  Skipping, sample already exists on EcoTaxa")
            continue
        
        # Upload
        logger.info(f"  Uploading '{zip_path.name}' ({format_file_size(zip_path.stat().st_size)})...")
        upload_result = upload_file(logger, token, zip_path, timeout=ecotaxa_config.get("upload_timeout_seconds", 300))
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
        logger.info(f"  ✓ Upload completed")
        
        # Import
        logger.debug(f"Importing {sample_id}")
        server_directory = Path(server_path).stem
        import_result = import_file(logger, token, project_id, server_directory)
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
        success = monitor_job(logger, token, job_id)
        if success:
            logger.info(f"  ✓ Import completed")
        else:
            logger.warning(f"  ✗ Import failed or requires manual intervention")

    log_command_success(logger, "Upload")
