import subprocess
from pathlib import Path
import click
from cytoprocess.logging import setup_logging, log_command_success, log_command_start
from cytoprocess.utils import (
    list_sample_assets, path_to_sample_asset,
    raiseCytoError
)
from cytoprocess.commands import install


def run(ctx: click.Context, project: Path, force=False):
    # Housekeeping for the command
    logger = setup_logging(command="convert", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Converting .cyz files", project)
    if force:
        logger.debug("Force flag enabled: existing .json files will be overwritten")
    logger.debug("Context: %s", getattr(ctx, "obj", {}))


    # Get the path to Cyz2Json binary
    logger.debug("Getting path to Cyz2Json binary")
    try:
        cyz2json_path = install._check_or_get_cyz2json(logger)
    except Exception as e:
        raiseCytoError(f"Failed to get Cyz2Json binary: {e}", logger)
    

    # Detect possible set_definition.xml that overrides the default one included in .cyz file
    set_definition_path = project / "config" / "set_definition.xml"
    if set_definition_path.exists():
        logger.info(f"Using new set definition from '{set_definition_path}'")
        set_definition_command = ["--imaging-set-definition", str(set_definition_path)]
    else:
        logger.info(f"Using imaging set definitions from the .cyz file,\n  override with 'config/set_definition.xml' if needed")
        set_definition_command = []


    # Get .cyz files from raw directory
    cyz_files = list_sample_assets(project, kind="cyz", logger=logger, ctx=ctx)
    if not cyz_files:
        logger.warning(f"Then copy/move cyz files to '{project}/raw'")
        return
 

    # Convert each .cyz file
    for cyz_file in cyz_files:
        sample_id = cyz_file.stem
        logger.info(f"'{sample_id}'")
        json_path = path_to_sample_asset(sample_id, 'json', logger)
        json_file = project / json_path
        
        # Skip if JSON file already exists and force is not enabled
        if json_file.exists() and not force:
            logger.info(f"  Skipping, output file already exists (use --force to overwrite)")
            continue
        
        logger.info(f"  Converting to '{json_path}'")
        
        try:
            # Create sample directory if it doesn't exist
            json_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Build and log the command
            command = [cyz2json_path, str(cyz_file), "--raw", "--imaging-set-information", "--image-processing", "--image-processing-margin-percentage 0"]
            command.extend(set_definition_command)
            command.extend(["--output", str(json_file)])
            logger.debug(f"Running command: {' '.join(command)}")
            
            # Run Cyz2Json to convert the file
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True
            )
            # NB: we cannot trust result.returncode which is always 0 even when the conversion fails
            if result.stderr == '':
                logger.debug(f"Successfully converted '{cyz_file.name}'")
            else:
                logger.error(f"Conversion of '{cyz_file.name}' failed, see log for details")
                logger.debug(f"Cyz2Json output:\n{result.stdout}\n{result.stderr}")
        except subprocess.CalledProcessError as e:
            raiseCytoError(f"Failed to convert '{cyz_file.name}': {e.stderr}", logger)
        except Exception as e:
            raiseCytoError(f"Error converting '{cyz_file.name}': {e}", logger)

    log_command_success(logger, "Convert")
