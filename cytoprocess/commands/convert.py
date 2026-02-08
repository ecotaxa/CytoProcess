import logging
import subprocess
from pathlib import Path
from cytoprocess.utils import get_sample_files, ensure_project_dir, log_command_success, setup_logging, log_command_start, raiseCytoError
from cytoprocess.commands import install


def run(ctx, project, force=False):
    logger = setup_logging(command="convert", project=project, debug=ctx.obj["debug"])

    log_command_start(logger, "Converting .cyz files", project)
    
    if force:
        logger.debug("Force flag enabled: existing .json files will be overwritten")
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    # Get .cyz files from raw directory
    cyz_files = get_sample_files(project, logger, kind="cyz", ctx=ctx)
    if (not cyz_files):
        return
    
    # Get the path to Cyz2Json binary
    logger.debug("Getting path to Cyz2Json binary")
    try:
        cyz2json_path = install._check_or_get_cyz2json(logger)
    except Exception as e:
        raiseCytoError(f"Failed to get Cyz2Json binary: {e}", logger)
        
    # Create processed directory if it doesn't exist
    converted_dir = ensure_project_dir(project, "converted")

    # Convert each .cyz file
    for cyz_file in cyz_files:
        json_file = converted_dir / (cyz_file.stem + ".json")
        
        # Skip if JSON file already exists and force is not enabled
        if json_file.exists() and not force:
            logger.info(f"Skipping '{cyz_file.name}', json file already exists (use --force to overwrite)")
            continue
        
        logger.info(f"Converting\n  'raw/{cyz_file.name}' →\n  'converted/{json_file.name}'")
        
        try:
            # Build and log the command
            command = [cyz2json_path, str(cyz_file), "--raw", "--imaging-set-information","--output", str(json_file)]
            # TODO add --imaging-set-definition my_new_set_definition.xml as an option
            logger.debug(f"Running command: {' '.join(command)}")
            
            # Run Cyz2Json to convert the file
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True
            )
            logger.debug(f"Successfully converted '{cyz_file.name}'")
        except subprocess.CalledProcessError as e:
            raiseCytoError(f"Failed to convert '{cyz_file.name}': {e.stderr}", logger)
        except Exception as e:
            raiseCytoError(f"Error converting '{cyz_file.name}': {e}", logger)

    log_command_success(logger, "Convert")
