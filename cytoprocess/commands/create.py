import shutil
from pathlib import Path

from cytoprocess.utils import setup_logging, log_command_start, log_command_success


def run(ctx, project):
    # Housekeeping for the command
    logger = setup_logging(command="create", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Creating project", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    

    # Create the main directory if it doesn't exist
    if (Path(project).exists()):
        logger.info(f"Project directory '{project}' already exists,\nChecking its contents...")
    else:
        logger.info(f"Creating project directory '{project}'.")
        project.mkdir(parents=True, exist_ok=True)
    
    # List of subdirectories to create
    # NB: others will be created on the fly by the other commands
    subdirectories = ["raw", "meta", "config"]
    
    # Create each subdirectory
    for subdir in subdirectories:
        subdir_path = project / subdir
        subdir_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created/checked subdirectory '{subdir_path}'")
    
    # Copy metadata configuration template to config directory
    template_file = Path(__file__).parent.parent / "templates" / "config.yaml"
    dest_file = Path(project) / "config" / "config.yaml"
    if not dest_file.exists():
        logger.debug(f"Copying configuration template to '{dest_file}'")
        shutil.copyfile(template_file, dest_file)
    else:
        logger.debug(f"Configuration file already exists at '{dest_file}'")

    log_command_success(logger, "Create project")
