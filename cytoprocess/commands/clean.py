import logging
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import click

from cytoprocess.logging import setup_logging, log_command_start, log_command_success
from cytoprocess.utils import raiseCytoError

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
        logger.warning(f"Directory does not exist: '{directory}'")
        return False
    
    try:
        shutil.rmtree(directory)
        logger.info(f"Successfully removed '{directory}'")
        return True
    except Exception as e:
        raiseCytoError(f"Error removing directory: {e}", logger)


def run(ctx: click.Context, project: Path, older_than: int = None):
    # Housekeeping for the command
    logger = setup_logging(command="cleanup", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Cleaning up intermediate files", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    # Remove intermediate storage for metadata
    work_dir = project / "work"
    _remove_directory(work_dir, logger)

    # Remove old log files
    log_dir = project / "logs"
    if log_dir.exists() and older_than is not None:
        cutoff_date = date.today() - timedelta(days=older_than)
        
        nb_removed = 0
        for log_file in log_dir.glob("*_cytoprocess.log"):
            try:
                date_str = log_file.stem.split("_")[0]
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                
                if file_date < cutoff_date:
                    logger.debug(f"Removing log file '{log_file}'")
                    log_file.unlink()
                    nb_removed += 1
            except (ValueError, IndexError) as e:
                logger.warning(f"Could not parse date from log file '{log_file}': {e}")
        logger.info(f"Successfully removed {nb_removed} log files older than {older_than} days")
  
    log_command_success(logger, "Cleanup")
