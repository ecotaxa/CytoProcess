import base64
import shutil
from cytoprocess.utils import list_sample_assets, path_to_sample_asset, get_json_section, setup_logging, log_command_start, log_command_success, raiseCytoError
import imageio as iio
from pathlib import Path
import numpy as np


def _add_scale_bar(img: np.ndarray, pixel_size: float):
    """
    Add a scale bar at the bottom of the image
    
    Args:
        input_img: NumPy array representing the source image
        pixel_size: Size of one pixel in um

    Returns:
        NumPy array of the image with the scale bar added at the bottom
    """

    # Define a custom minimal 'font' for scale bar text
    f2 = np.asarray(
        [[1,1,0,0,1,1],
         [1,0,1,1,0,1],
         [1,1,1,1,0,1],
         [1,1,1,0,1,1],
         [1,1,0,1,1,1],
         [1,0,1,1,1,1],
         [1,0,0,0,0,1],
         [1,1,1,1,1,1],
         [1,1,1,1,1,1]])
    f0 = np.asarray(
        [[1,1,0,0,1,1],
         [1,0,1,1,0,1],
         [1,0,1,1,0,1],
         [1,0,1,1,0,1],
         [1,0,1,1,0,1],
         [1,0,1,1,0,1],
         [1,1,0,0,1,1],
         [1,1,1,1,1,1],
         [1,1,1,1,1,1]])
    fu = np.asarray(
        [[1,1,1,1,1,1],
         [1,1,1,1,1,1],
         [1,1,1,1,1,1],
         [1,0,1,1,0,1],
         [1,0,1,1,0,1],
         [1,0,1,1,0,1],
         [1,0,0,0,1,1],
         [1,0,1,1,1,1],
         [1,0,1,1,1,1]])
    fm = np.asarray(
        [[1,1,1,1,1,1],
         [1,1,1,1,1,1],
         [1,1,1,1,1,1],
         [0,0,1,0,1,1],
         [0,1,0,1,0,1],
         [0,1,0,1,0,1],
         [0,1,0,1,0,1],
         [1,1,1,1,1,1],
         [1,1,1,1,1,1]])
    
    
    # Define scale bar (20µm for all images)
    bar_width_px = int(20 / pixel_size)
    bar_text = np.concatenate((f2, f0, fu, fm), axis=1)
    text_height_px,text_width_px = bar_text.shape

    # Define the width and height of the scale bar area
    img_width_px = img.shape[1]
    pad = 5   # start the scale bar at these many pixels from the bottom left corner
    w = max(img_width_px, bar_width_px+pad, text_width_px+pad)
    h = 31
    # NB: 31px matches ZooProcess
    
    # Define the scale bar area background colour as the median of the top row of the image
    backgd_clr = np.median(img[0,:]) 

    # Pad the input image on the right if it is not wide enough
    if w > img_width_px:
        padding_width = w - img_width_px
        img = np.pad(img, ((0, 0), (0, padding_width)), constant_values=backgd_clr)
    
    # Draw a blank scale bar area
    scale = np.full((h, w), backgd_clr, dtype=img.dtype)
    # Add the scale bar (black)
    scale[h-pad-2:h-pad, pad:(bar_width_px+pad)] = 0
    # Add the text (convert [0,1] to [0,backgd_clr])
    scale[h-pad-4-text_height_px:h-pad-4, pad:(text_width_px+pad)] = (bar_text * backgd_clr).astype(img.dtype)
    
    # Combine with the image
    img = np.concatenate((img, scale), axis=0)
        
    return img


def _add_scale_bar_multiprocessing(args):
    """Wrapper for multiprocessing, with arguments as a single tuple."""
    image_file, processed_path, pixel_size = args
    return _add_scale_bar(image_file, processed_path, pixel_size)



def run(ctx, project, force=False):
    # Housekeeping for the command
    logger = setup_logging(command="extract_images", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Extracting images", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    if force:
        logger.debug("Force flag enabled, existing image directories will be removed and recreated")


    # Get JSON files from converted directory
    json_files = list_sample_assets(project, kind="json", logger=logger, ctx=ctx)
    if not json_files:
        return   
    logger.info(f"Processing {len(json_files)} .json file(s)")
    
    # Process each JSON file
    total_images = 0
    for json_file in json_files:
        # Get sample_id from file name
        sample_id = json_file.parents[0].name
        images_dir = project / path_to_sample_asset(sample_id, 'images', logger)

        logger.info(f"'{sample_id}'")

        try:
            logger.debug(f"Extracting images from '{json_file.name}'")
                        
            # Check if directory already exists
            if images_dir.exists():
                if force:
                    logger.info(f"  Removing existing directory: '{images_dir}'")
                    shutil.rmtree(images_dir)
                else:
                    logger.info(f"  Skipping, output directory already exists (use --force to overwrite).")
                    continue
            
            images = get_json_section(json_file, 'images', logger)

            if images is None:
                logger.warning(f"No images found in '{json_file.name}'")
                continue

            # Create the directory
            images_dir.mkdir(parents=True, exist_ok=True)

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
                    # NB: this is already JPG encoded data
                except Exception as e:
                    logger.error(f"Failed to decode base64 for particle {particle_id} in '{json_file.name}': {e}")
                    continue
                
                # read as an image
                img = iio.imread(image_data)

                # Add scale bar to the image
                img = _add_scale_bar(img, pixel_size=0.5)
                # TODO do this in parallel for all images?
                # TODO get pixel size from the JSON file (instrument->measurementSettings->CytoSettings->iif->PixelSize)

                # Write to JPG file
                # (there is no point in saving as .png since the original data is already JPG compressed)
                output_file = images_dir / f"{particle_id}.jpg"
                with open(output_file, 'wb') as img_file:
                    iio.imwrite(img_file, img, format='jpg')
                
                image_count += 1
                    
            logger.info(f"  Extracted {image_count} images to\n  '{images_dir}'")
            total_images += image_count
                
        except Exception as e:
            raiseCytoError(f"Error processing '{json_file.name}': {e}", logger)
    
    logger.info(f"Total images extracted: {total_images}")
    log_command_success(logger, "Extract images")

# TODO add a way to post process the images to remove the background and crop them when they are full frames
# background = instrument['measurementSettings']['CytoSettings']['CytoSettings']['iif']['Background'].get('Data')
# background_data = base64.b64decode(background)
# output_file = Path(project) / "background.png"
# with open(output_file, 'wb') as img_file:
#     img_file.write(background_data)