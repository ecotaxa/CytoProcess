import logging
import base64
import shutil
from pathlib import Path
from cytoprocess.utils import get_sample_files, ensure_project_dir, get_json_section, setup_logging, log_command_start, log_command_success, raiseCytoError


def run(ctx, project, force=False):
    logger = setup_logging(command="extract_images", project=project, debug=ctx.obj["debug"])

    log_command_start(logger, "Extracting images", project)
    
    if force:
        logger.debug("Force flag enabled, existing image directories will be removed and recreated")
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    # Get JSON files from converted directory
    json_files = get_sample_files(project, logger, kind="json", ctx=ctx)
    if not json_files:
        return
   
    logger.info(f"Processing {len(json_files)} .json file(s)")
    
    # Process each JSON file
    total_images = 0
    for json_file in json_files:
        logger.info(f"'{json_file.stem}'")

        try:
            logger.debug(f"Extracting images from '{json_file.name}'")
            
            # Define subdirectory for this sample's images
            sample_name = json_file.stem
            sample_images_dir = Path(project) / "images" / sample_name
            
            # Check if directory already exists
            if sample_images_dir.exists():
                if force:
                    logger.info(f"  Removing existing directory: '{sample_images_dir}'")
                    shutil.rmtree(sample_images_dir)
                else:
                    logger.info(f"  Skipping, output directory already exists (use --force to overwrite).")
                    continue
            
            # Create the directory
            sample_images_dir = ensure_project_dir(project, f"images/{sample_name}")
            
            images = get_json_section(json_file, 'images', logger)

            if images is None:
                logger.warning(f"No images found in '{json_file.name}'")
                continue
            
            image_count = 0
            for image in images:
                # Extract particleId and base64 data
                particle_id = image.get('particleId')
                base64_data = image.get('base64')
                
                if particle_id is None:
                    logger.warning(f"Image item missing 'particleId' in '{json_file.name}'")
                    continue
                
                if base64_data is None:
                    logger.warning(f"Image item {particle_id} missing 'base64' data in '{json_file.name}'")
                    continue
                
                # Decode base64 data
                try:
                    image_data = base64.b64decode(base64_data)
                except Exception as e:
                    logger.error(f"Failed to decode base64 for particle {particle_id} in '{json_file.name}': {e}")
                    continue
                
                # Write to JPG file (the data is JPG encoded already)
                output_file = sample_images_dir / f"{particle_id}.jpg"
                with open(output_file, 'wb') as img_file:
                    img_file.write(image_data)
                
                image_count += 1
                    
            logger.info(f"  Extracted {image_count} images to\n  '{sample_images_dir}'")
            total_images += image_count
                
        except Exception as e:
            raiseCytoError(f"Error processing '{json_file.name}': {e}", logger)
    
    logger.info(f"Total images extracted: {total_images}")
    log_command_success(logger, "Extract images")

# TODO add a way to post process the images to remove the background and crop them when they are full frames