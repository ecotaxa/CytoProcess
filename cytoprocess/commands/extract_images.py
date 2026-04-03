import base64
import logging
import os
import shutil
from functools import partial
from multiprocessing import Pool
from pathlib import Path

import click
import imageio as iio
import numpy as np
import pandas as pd
from scipy import ndimage
from skimage import measure, morphology

from cytoprocess.logging import setup_logging, log_command_start, log_command_success
from cytoprocess.project import list_sample_assets, path_to_sample_asset
from cytoprocess.utils import get_json_section, raiseCytoError
from cytoprocess.utils import imshow


def _crop_background(background_img: np.ndarray, crop: dict, img_shape: tuple) -> np.ndarray:
    """
    Extract and save the background crop corresponding to the image crop region.
    
    Args:
        background_img: Full background image as numpy array
        crop: Dictionary with keys 'X', 'Y', 'Width', 'Height' defining the crop rectangle
        img_shape: Shape of the image (height, width)
        
    Returns:
        Cropped background region as numpy array
    """
    # Extract bbox coordinates
    x = int(crop.get('X', 0))
    y = int(crop.get('Y', 0))
    width = int(crop.get('Width', img_shape[1]))
    height = int(crop.get('Height', img_shape[0]))

    # Correct a bug when the crop is the full background image
    if x == 0 and width == (img_shape[1] - 1):
        width += 1
    if y == 0 and height == (img_shape[0] - 1):
        height += 1

    # Extract corresponding background region
    x2 = x + width
    y2 = y + height
    bkg = background_img[y:y2, x:x2]
    
    return bkg


def mad(x):
    """Compute the median absolute deviation of a 1D array or list."""
    med = np.median(x)
    mad = np.median(np.absolute(x - med))
    return (mad, med)


def mm(x, y_min = 3, y_max = 20, Km = 50000):
    """
    Returns an integer y that increases with x (Michaelis-Menten kinetics)

    Args:
        x: integer between 0 and +Inf
        ymin, ymax: low and high bounds of the output
        Km: half-saturation constant (x value at which y = (y_min + y_max) / 2)
    Returns:
        y: integer between ymin and ymax
    """
    y = y_min + (y_max - y_min) * x / (Km + x)
    return np.round(y).astype(int)


def _fast_particle_area(x):
    """Compute the area of a particle from region props in a fast way"""
    return(np.sum(x._label_image[x._slice] == x.label))


def _get_largest_region(msk):
    """
    Get the largest connected region from a binary mask
    
    Args:
        msk: Binary mask as a numpy array

    Returns:
        Binary mask of the largest region, or None if no regions found
    """
    lab = measure.label(msk)
    if lab.max() == 0:
        # No regions found, return the original mask (which is empty)
        return msk

    reg = measure.regionprops(lab)    
    largest_region = max(reg, key=lambda r: _fast_particle_area(r))
    msk = (lab == largest_region.label)
    return msk


def _segment_particle(id: str, img: np.ndarray, bkg: np.ndarray, logger: logging.Logger) -> np.ndarray:
    """
    Segment the particle from the background using a custom algorithm based on background subtraction and morphological operations.
    """
    # imshow(img)
    # imshow(bkg)

    ## 1/ Subtract the background
    pro = img.astype(np.float32) / bkg.astype(np.float32)
    # background is ~ 1
    # darker regions are lower than background -> < 1
    # lighter regions are higher than background -> > 1

    ## 2/ Threshold
    # define background statistics from the borders of the image,
    # which are more likely to be pure background
    borders = np.concatenate((pro[0:3,:].flatten(), pro[-3:-1,:].flatten(),
                              pro[:,0:3].flatten(), pro[:,-3:-1].flatten()))
    bkg_mad, bkg_med = mad(borders)

    # select significantly different-than-background regions
    pro = pro - bkg_med
    #     lighter               or darker
    msk = (pro > (bkg_mad * 4)) | (pro < -(bkg_mad * 3))
    # NB: increasing the mad multiplier here reduces the region selected

    ## 3/ Refine the mask
    # remove small objects
    msk = morphology.remove_small_objects(msk, max_size=10)
    # dilate a bit, erode a bit, and close the remaining holes
    msk = morphology.closing(msk, morphology.disk(3))
    # fill holes within the masks
    msk = ndimage.binary_fill_holes(msk)
    # keep only the largest connected region
    # if no regions are left, this returns None
    msk = _get_largest_region(msk)

    # if the mask is already empty, just stop
    if not msk.any():
        return msk

    ## 4/ Eliminate light halos = 
    # Extract the external edge of the mask to check if it is light
    # Erode the mask to remove the light regions

    # Make the size of the edge proportional to the size of the object,
    # to inscpect a consistent region around the object, regardless of its size
    area = np.sum(msk)
    disk_radius = mm(area)
    # Define the edge of the object
    edge = msk & ~morphology.erosion(msk, morphology.disk(disk_radius))
    
    # If the edge is often lighter than the background,
    # then we are likely in the presence of a halo
    if (img[edge] > 1.05 * bkg[edge]).mean() > 0.2:
        # Remove the light parts of the edge of the object from the mask
        in_halo = (img > bkg) & edge
        msk[in_halo] = False

        # Fill holes again, in case this created new ones
        msk = ndimage.binary_fill_holes(msk)

        # Get only the largest particule again,
        # in case the erosion created several disconnected regions
        msk = _get_largest_region(msk)

    return msk


def _extract_features(mask: np.ndarray, image: np.ndarray) -> dict | None:
    """
    Extract morphological and intensity features from a segmented particle.
    
    Args:
        mask: Binary mask of the particle
        image: Original grayscale image
        
    Returns:
        Dictionary of features or None if the mask is empty (no particle found)
    """
    # Label the mask (should be single region)
    labeled = measure.label(mask)

    if labeled.max() == 0:
        return None    
    
    # Extract relevant features
    props = ['area', 'area_filled', 'convex_area',
             'axis_major_length', 'axis_minor_length', 'feret_diameter_max',
             'eccentricity',
             'moments_hu',
             'intensity_max', 'intensity_mean', 'intensity_median', 'intensity_min', 'intensity_std',
              'perimeter', 'perimeter_crofton',
              'solidity']
    features_table = measure.regionprops_table(labeled, intensity_image=image, properties=props)
    
    return features_table


def _add_scale_bar(img: np.ndarray, pixel_size: float) -> np.ndarray:
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


def _process_single_image(image: dict, background_img: np.ndarray,
                          pixel_size: float, sample_id: str, images_dir: Path, logger: logging.Logger) -> tuple[dict | None, bool, str | None]:
    """
    Process a single image. Returns a tuple of (row_dict, success, error_msg).
    This function is designed to run in parallel.
    """
    try:
        # Extract elements for the current image
        particle_id = image.get('particleId')                
        if particle_id is None:
            return (None, False, f"Image missing the 'particleId' field")
        
        base64_data = image.get('base64')
        if base64_data is None:
            return (None, False, f"Image {particle_id} missing 'base64' data")

        crop = image.get('cropRectangle')
        if crop is None:
            return (None, False, f"Image {particle_id} missing 'cropRectangle'")

        # Decode base64 data
        try:
            image_data = base64.b64decode(base64_data)
        except Exception as e:
            return (None, False, f"Failed to decode base64 for particle {particle_id}: {e}")
        
        # Read as an image
        img = iio.imread(image_data)
        # base_path = str( images_dir / f"{particle_id}.jpg")
        # with open(base_path.replace('.jpg', '_rawimg.jpg'), 'wb') as img_file:
        #     iio.imwrite(img_file, img, format='jpg', quality=100)

        # Segment the particle
        bkg = _crop_background(background_img, crop, img.shape)
        # with open(base_path.replace('.jpg', '_rawbkg.jpg'), 'wb') as img_file:
        #     iio.imwrite(img_file, bkg, format='jpg', quality=100)
        img_mask = _segment_particle(particle_id, img, bkg, logger)
        
        # Add scale bar to the image and the mask
        img = _add_scale_bar(img, pixel_size=pixel_size)
        img_mask = _add_scale_bar(img_mask, pixel_size=pixel_size)

        # Extract features from the particle
        features = _extract_features(img_mask, img)
        if features is None:
            return (None, False, f"  No object detected on image {particle_id}")

        # Write the image and mask from the worker process to avoid having to return them
        output_file = images_dir / f"{particle_id}_img.jpg"
        with open(output_file, 'wb') as img_file:
            iio.imwrite(img_file, img, format='jpg', quality=98)

        output_file = images_dir / f"{particle_id}_mask.png"
        with open(output_file, 'wb') as img_file:
            iio.imwrite(img_file, (img_mask * 255).astype(np.uint8), format='png')

        # Create a DataFrame row with identifiers and features
        row = {
            'sample_id': sample_id,
            'object_id': f"{sample_id}_{particle_id}"
        }
        
        # Add features, with the object_ prefix
        for key, value in features.items():
            row[f"object_{key}"] = value[0]

        return (row, True, None)
        
    except Exception as e:
        return (None, False, str(e))


def run(ctx: click.Context, project: Path, force=False, max_cores=None):
    # Housekeeping for the command
    logger = setup_logging(command="extract_images", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Extracting images", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    if force:
        logger.debug("Force flag enabled, existing image directories will be removed and recreated")

    # Determine number of cores to use
    available_cores = os.cpu_count() or 1
    n_cores = max(1, available_cores - 1)
    if max_cores is not None:
        n_cores = min(n_cores, max_cores)
    logger.debug(f"Using {n_cores} core(s) for parallel processing")


    # Get JSON files from converted directory
    json_files = list_sample_assets(project, kind="json",
                                    logger=logger, samples_mask=ctx.obj["sample"])
    if not json_files:
        return   
    logger.info(f"Processing {len(json_files)} .json file(s)")
    
    # Process each JSON file
    for json_file in json_files:
        # Get sample_id from file name
        sample_id = json_file.parents[0].name
        # and define output paths based on it
        images_dir = project / path_to_sample_asset(sample_id, 'images', logger)
        features_file = project / path_to_sample_asset(sample_id, 'image_features', logger)

        logger.info(f"'{sample_id}'")

        try:
            logger.debug(f"Extracting images from '{json_file.name}'")
                        
            # Check if directory already exists
            if images_dir.exists() and features_file.exists():
                if force:
                    logger.info(f"  Removing existing data")
                    shutil.rmtree(images_dir)
                    features_file.unlink(missing_ok=True)
                else:
                    logger.info(f"  Skipping, outputs already exist (use --force to overwrite).")
                    continue
            
            # Extract the images section from the JSON file
            images = get_json_section(json_file, 'images', logger)
            if images is None:
                logger.warning(f"No images found in '{json_file.name}'")
                continue

            # Get the background image from the JSON file
            instrument = get_json_section(json_file, 'instrument', logger)
            background_data = instrument['measurementSettings']['CytoSettings']['CytoSettings']['iif']['Background'].get('Data')
            if background_data is not None:
                background_data = base64.b64decode(background_data)
                background_img = iio.imread(background_data)
                # For some reason, this is a RGB image,
                # convert to grayscale by averaging the channels
                background_img = background_img.mean(axis=2).astype(np.uint8)
            else:
                logger.warning(f"No background image found in '{json_file.name}', using a uniform grey background instead")
                background_img = np.ones((1200,1920), dtype=np.uint8) * 150

            # Extract the pixel size from the JSON file
            pixel_size = instrument['measurementSettings']['CytoSettings']['CytoSettings']['iif']['ImageScaleMuPerPixelP']

            # Create the directory
            images_dir.mkdir(parents=True, exist_ok=True)

            # Process images in parallel
            if ctx.obj["debug"]:
                logger.debug("Debug mode enabled, processing images sequentially")
                results = [_process_single_image(image, background_img, pixel_size, sample_id, images_dir, logger) for image in images]
            else:
                num_workers = min(n_cores, len(images))  # Don't create more workers than images
                logger.debug(f"Processing {len(images)} images using {num_workers} workers")
                
                with Pool(num_workers) as pool:
                    process_func = partial(_process_single_image, background_img=background_img, 
                                        pixel_size=pixel_size, sample_id=sample_id, images_dir=images_dir, logger=logger)
                    results = pool.map(process_func, images)
            
            # Process results
            image_count = 0
            rows = []
            for row, success, error_msg in results:
                if not success:
                    logger.warning(error_msg)
                    continue
                
                rows.append(row)
                
                image_count += 1
                    
            logger.info(f"  Extracted {image_count} images to\n  '{images_dir}'")

            # Create features DataFrame and save to Parquet
            df = pd.DataFrame(rows)
            df = df.sort_values('object_id').reset_index(drop=True)
            df.to_parquet(features_file, index=False)
            
            logger.info(f"  Saved {df.shape[1]} properties for each image to\n  '{features_file}'")

        except Exception as e:
            raiseCytoError(f"Error processing '{sample_id}': {e}", logger)
    
    log_command_success(logger, "Extract images")
