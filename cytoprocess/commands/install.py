import os
import shutil
import platform
import subprocess
import urllib.request
import json
import tempfile
import zipfile
from pathlib import Path
from cytoprocess.utils import log_command_start, log_command_success, setup_logging, raiseCytoError


def _get_or_create_bin_dir() -> Path:
    """Get (and create if necessary) the directory for storing executables."""
    bin_dir = Path.home() / ".bin"

    # create the directory if it doesn't exist
    bin_dir.mkdir(parents=True, exist_ok=True)
    
    return bin_dir


def _get_executable_name() -> str:
    """Define the name of the cyz2json executable based on OS."""
    executable_name = "Cyz2Json.exe" if platform.system() == "Windows" else "Cyz2Json"
    return executable_name


def _get_release_file_name(logger) -> str:
    """Get the appropriate release file name based on OS."""
    system = platform.system().lower()
    
    if system == "darwin":  # macOS
        release_file = "cyz2json-macos-latest.zip"
    elif system == "linux":
        release_file = "cyz2json-ubuntu-latest.zip"
    elif system == "windows":
        release_file = "cyz2json-windows-latest.zip"
    else:
        raiseCytoError(f"Unsupported OS: {system}", logger)
    
    logger.debug(f"Determined release file name: {release_file}")
    return release_file


def _download_latest_release(logger) -> str:
    """Download the latest release of cyz2json and return the path to the executable."""
    # 1. Fetch latest release info from GitHub API
    logger.info("Fetching latest cyz2json release info from GitHub")
    
    # get list of files in latest release
    api_url = "https://api.github.com/repos/OBAMANEXT/cyz2json/releases/latest"
    try:
        with urllib.request.urlopen(api_url) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        raiseCytoError(f"Failed to fetch latest release: {e}", logger)
    
    # search for the appropriate release file
    release_file = _get_release_file_name(logger)
    assets = data.get("assets", [])
    
    matching_asset = None
    for asset in assets:
        if release_file in asset["name"]:
            matching_asset = asset
            break
    
    if not matching_asset:
        available_assets = [a["name"] for a in assets]
        raiseCytoError(f"No file {release_file} within {available_assets}", logger)
    
    # 2. Download and extract the appropriate release file
    logger.info(f"Downloading and installing {matching_asset['name']}")
    
    download_url = matching_asset["browser_download_url"]
    logger.debug(f"Downloading from {download_url}")
    
    # we are actually downloading a bunch of files
    # determine where to store them
    bin_dir = _get_or_create_bin_dir()
    cyz2json_dir = bin_dir / "cyz2json_dlls"
    
    try:
        # download to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp_path = tmp.name
        urllib.request.urlretrieve(download_url, tmp_path)
        logger.debug(f"Downloaded to {tmp_path}")
        
        # clean up the existing cyz2json_dir if it exists
        if cyz2json_dir.exists():
            logger.debug(f"Removing existing cyz2json directory at {cyz2json_dir}")
            shutil.rmtree(cyz2json_dir)
                    
        # extract the zip file
        cyz2json_dir.mkdir(parents=True)
        logger.debug(f"Extracting to {cyz2json_dir}")
        with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
            zip_ref.extractall(cyz2json_dir)
        
        # clean up temporary file
        logger.debug(f"Removing temporary file {tmp_path}")
        os.remove(tmp_path)
       
        # create symlink in bin_dir
        # define symkink source and name
        executable_path = cyz2json_dir / _get_executable_name()
        symlink_path = bin_dir / _get_executable_name()
        
        # make the exectuable actually executable
        logger.debug(f"Setting execute permissions for {executable_path}")
        os.chmod(executable_path, 0o755)

        # remove existing symlink if it exists
        if symlink_path.exists() or symlink_path.is_symlink():
            logger.debug(f"Removing existing symlink at {symlink_path}")
            symlink_path.unlink()
        
        # create symlink
        logger.debug(f"Creating symlink at {symlink_path} -> {executable_path}")
        os.symlink(executable_path, symlink_path)

        logger.debug(f"Successfully installed cyz2json to {symlink_path}")
    
    except Exception as e:
        raiseCytoError(f"Failed to download and install cyz2json: {e}", logger)
    
    return str(symlink_path)


def _check_or_get_cyz2json(logger, force: bool = False) -> str:
    """Get the path to the cyz2json executable, downloading if necessary."""
    bin_dir = _get_or_create_bin_dir()
    executable_name = _get_executable_name()
    executable_path = bin_dir / executable_name

    if force:
        logger.info("Downloading latest cyz2json release")
        return _download_latest_release(logger)
    
    if not executable_path.exists():
        logger.info(f"cyz2json not found at {executable_path}, downloading")
        return _download_latest_release(logger)
    
    logger.debug(f"Using existing cyz2json at {executable_path}")
    return str(executable_path)


def run(ctx, force: bool = False):
    logger = setup_logging(command="install", project=None, debug=ctx.obj["debug"])
    log_command_start(logger, "Installing cyz2json", project=None)
    try:
        path = _check_or_get_cyz2json(force=force, logger=logger)
        result = subprocess.run([path, '--version'], check=True, capture_output=True, text=True)
        logger.info(f"cyz2json available at {path}, at version {result.stdout.strip()}")
    except Exception as e:
        raiseCytoError(f"Failed to install cyz2json: {e}", logger)
        raise

    log_command_success(logger, "Install cyz2json")
