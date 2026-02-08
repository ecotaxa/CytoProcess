import logging
from pathlib import Path
import shutil
from cytoprocess.utils import setup_logging, log_command_start, log_command_success, raiseCytoError


def _remove_directory(directory: Path, logger: logging.Logger) -> bool:
    """Remove a directory and all its contents.
    
    Args:
        directory: Path to the directory to remove
        logger: Logger instance for logging operations
        
    Returns:
        bool: True if directory was removed, False if it didn't exist
    """
    
    logger.debug(f"Checking if '{directory}' exists")
    if not directory.exists():
        logger.info(f"Directory does not exist: '{directory}'")
        return False
    
    try:
        shutil.rmtree(directory)
        logger.info(f"Successfully removed '{directory}'")
        return True
    except Exception as e:
        raiseCytoError(f"Error removing directory: {e}", logger)


def run(ctx, project):
    logger = setup_logging(command="cleanup", project=project, debug=ctx.obj["debug"])

    log_command_start(logger, "Cleaning up intermediate files", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    # Remove directory containing .json files
    # (they are large and can be reconverted from .cyz files)
    converted_dir = Path(project) / "converted"
    _remove_directory(converted_dir, logger)

    # Remove intermediate storage for metadata
    work_dir = Path(project) / "work"
    _remove_directory(work_dir, logger)

    # Remove directory with individual images
    images_dir = Path(project) / "images"
    _remove_directory(images_dir, logger)
  
    log_command_success(logger, "Cleanup")
