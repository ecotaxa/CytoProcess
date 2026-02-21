import logging
import os
import numpy as np
import pandas as pd
from pathlib import Path
from multiprocessing import Pool
from skimage import io, feature, morphology, measure, filters
from scipy import ndimage
from cytoprocess.utils import ensure_project_dir, log_command_start, log_command_success, setup_logging, raiseCytoError


def _segment_particle(image):
    """
    Segment the largest particle from an image using edge detection and morphological operations.
    
    Args:
        image: Grayscale image as numpy array
        
    Returns:
        Binary mask of the largest particle, or None if no particle found
    """
    # Apply Canny edge detection
    edges = feature.canny(image, sigma=1.0)
    
    # Fill edges to create solid regions
    filled = ndimage.binary_fill_holes(edges)
    
    # Apply threshold if filling didn't work well
    if filled.sum() < 10:
        # Use Otsu's threshold as fallback
        thresh_val = filters.threshold_otsu(image)
        filled = image > thresh_val
    
    # Morphological operations: dilate then erode (closing) to clean up
    dilated = morphology.dilation(filled, morphology.disk(2))
    cleaned = morphology.erosion(dilated, morphology.disk(2))
    
    # Label connected regions
    labeled = measure.label(cleaned)
    
    if labeled.max() == 0:
        return None
    
    # Find the largest region
    regions = measure.regionprops(labeled)
    if not regions:
        return None
    
    largest_region = max(regions, key=lambda r: _fast_particle_area(r))
    
    # Create mask for largest region only
    mask = labeled == largest_region.label
    
    return mask


def _fast_particle_area(x):
    return(np.sum(x._label_image[x._slice] == x.label))


def _extract_features(mask, image):
    """
    Extract morphological and intensity features from a segmented particle.
    
    Args:
        mask: Binary mask of the particle
        image: Original grayscale image
        
    Returns:
        Dictionary of features
    """
    # Label the mask (should be single region)
    labeled = measure.label(mask)

    if labeled.max() == 0:
        return None    
    
    # Extract relevant features
    props = ['area', 'area_filled', 'axis_major_length', 'axis_minor_length', 
             'eccentricity', 'feret_diameter_max', 'intensity_max', 'intensity_mean',
             'intensity_median', 'intensity_min', 'intensity_std', 'perimeter', 'solidity']
    features_table = measure.regionprops_table(labeled, intensity_image=image, properties=props)
    
    return features_table


def _process_single_image(args):
    """
    Process a single image file and return features.
    
    Args:
        args: Tuple of (image_file, sample_id, logger)
        
    Returns:
        Dictionary of features with identifiers, or None if processing failed
    """
    image_file, sample_id, logger = args
    particle_id = image_file.stem
   
    try:
        # Read image as grayscale
        image = io.imread(image_file, as_gray=True)
        
        # Segment the particle
        mask = _segment_particle(image)
        
        if mask is None:
            logger.warning(f"Could not segment particle in image {image_file.name}")
            return None
        
        # Extract features
        features = _extract_features(mask, image)
        
        if features is None:
            logger.warning(f"Could not extract features from particle in image {image_file.name}")
            return None
        
        # Create row with identifiers and features
        row = {
            'sample_id': sample_id,
            'object_id': f"{sample_id}_{particle_id}"
        }
        
        # Add features, with the object_ prefix
        for key, value in features.items():
            row[f"object_{key}"] = value[0]
        
        return row
        
    except Exception as e:
        logger.error(f"Error processing image {image_file.name}: {e}")
        return None


def run(ctx, project, force=False, max_cores=None):
    logger = setup_logging(command="compute_features", project=project, debug=ctx.obj["debug"])

    log_command_start(logger, "Computing image features", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    # Determine number of cores to use
    available_cores = os.cpu_count() or 1
    n_cores = max(1, available_cores - 1)
    if max_cores is not None:
        n_cores = min(n_cores, max_cores)
    logger.debug(f"Using {n_cores} core(s) for parallel processing")
    
    # Check images directory exists
    images_dir = Path(project) / "images"
    if not images_dir.exists():
        raiseCytoError(f"Images directory not found: '{images_dir}'. Run extract_images first.", logger)
    
    # Get list of sample directories
    sample_dirs = [d for d in images_dir.iterdir() if d.is_dir()]
    if not sample_dirs:
        raiseCytoError(f"No sample directories found in '{images_dir}', run 'cytoprocess extract_images {project}' first.", logger)
   
    # Filter by sample if specified in context
    sample = getattr(ctx, "obj", {}).get("sample")
    if sample:
        sample_dirs = [d for d in sample_dirs if d.name == sample]
        if not sample_dirs:
            raiseCytoError(f"No image directory found for sample '{sample}', run 'cytoprocess --sample '{sample}' extract_images {project}' first.", logger)
    
    logger.info(f"Processing {len(sample_dirs)} sample(s)")
    
    # Ensure work directory exists
    work_dir = ensure_project_dir(project, "work")
    
    # Process each sample directory
    for sample_dir in sample_dirs:
        sample_id = sample_dir.name
        output_file = work_dir / f"{sample_id}_image_features.parquet"
        
        logger.info(f"'{sample_id}'")

        # Skip if output file exists and force is not set
        if output_file.exists() and not force:
            logger.info(f"  Skipping, output file already exists (use --force to overwrite)")
            continue
        
        try:
            # Get all JPG images in sample directory
            logger.debug(f"Listing images for sample '{sample_id}'")
            image_files = sorted(sample_dir.glob("*.jpg"))
            
            if not image_files:
                logger.warning(f"No JPG images found in '{sample_dir}', run 'cytoprocess --sample '{sample_id}' extract_images {project}' first.", logger)
                continue
            
            logger.info(f"  {len(image_files)} images to process")
            
            # Prepare arguments for parallel processing
            args_list = [(image_file, sample_id, logger) for image_file in image_files]
            
            # Process images in parallel
            with Pool(processes=n_cores) as pool:
                results = pool.map(_process_single_image, args_list)
            
            # Filter out None results
            rows = [r for r in results if r is not None]
            
            logger.debug(f"Successfully processed {len(rows)}/{len(image_files)} images")
            
            if not rows:
                logger.warning(f"No features extracted for sample '{sample_id}'")
                continue
            
            # Create DataFrame and save to Parquet
            df = pd.DataFrame(rows)
            df = df.sort_values('object_id').reset_index(drop=True)
            df.to_parquet(output_file, index=False)
            
            logger.info(f"  Saved {df.shape[1]} properties for {df.shape[0]} images to\n  '{output_file}'")
            
        except Exception as e:
            raiseCytoError(f"Error processing sample '{sample_id}': {e}", logger)

    log_command_success(logger, "Compute features")
