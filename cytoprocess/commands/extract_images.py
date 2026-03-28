import base64
import shutil
import logging
from cytoprocess.utils import list_sample_assets, path_to_sample_asset, get_json_section, setup_logging, log_command_start, log_command_success, raiseCytoError
import imageio as iio
from skimage import morphology, measure
from scipy import ndimage
import numpy as np
import pandas as pd


def _rescale_pixel_values(img):
    """
    Rescale values in an images into the range [0, 255].
    Args:
        img: Input image as a numpy array
    Returns:
        Image with pixel values rescaled to the range [0, 255] as a numpy uint8 array
    """
    vmin = img.min()
    vmax = img.max()
    if vmax > vmin:
        return ((img - vmin) / (vmax - vmin) * 255.0).astype(np.uint8)
    else:
        return np.zeros_like(img, dtype=np.uint8)


def _clean_background(img: np.ndarray, background_img: np.ndarray, crop: dict) -> np.ndarray:
    """
    Remove the background based on the crop rectangle and the background image
    
    Args:
        img: Grayscale crop as numpy array
        background_img: Full background image as numpy array
        crop: Dictionary with keys 'X', 'Y', 'Width', 'Height' defining the crop rectangle in the original image coordinates
    
    Returns:
        Grayscale image with background cleaned up, as numpy array    
    """

    # Extract bbox coordinates
    x = int(crop.get('X', 0))
    y = int(crop.get('Y', 0))
    width = int(crop.get('Width', img.shape[1]))
    height = int(crop.get('Height', img.shape[0]))

    # Add reference black and white to ensure consistent dynamic range in the rescaling
    img_with_ref = np.concatenate((
        np.zeros((1, img.shape[1]), dtype=np.uint8),
        np.ones((1, img.shape[1]), dtype=np.uint8)*255,
        img), axis=0
    )

    # Extract corresponding background region
    x2 = x + width
    y2 = y + height + 2
    bkg = background_img[y:y2, x:x2]

    # Subtract background
    sub = img_with_ref.astype(np.float32) - bkg.astype(np.float32)
    
    # There is noise left around the background level
    # remove the values around 0 to clean it up
    threshold = 10
    sub[(sub < threshold) & (sub > -threshold)] = 0

    # Now rescale the values
    cleaned_img = _rescale_pixel_values(sub)
    
    # Remove the reference lines
    cleaned_img = cleaned_img[2:,:]

    return cleaned_img


# NB: This is not used but kept here for reference

# def _ifcb_segment_particle(img: np.ndarray) -> np.ndarray:
#     """
#     Segment the largest particle from an image using the IFCB algorithm.
#     
#     Adapted from https://gist.github.com/joefutrelle/ba5115b9f608c99e2bad
#     
#     Args:
#         img: Grayscale image as numpy array
#     Returns:
#         Binary mask of the largest particle
#     """
#     from phasepack import phasecong
#     # NB: needs pyfftw
#     import numpy as np
#     from scipy.cluster.vq import kmeans2
#     from skimage.morphology import closing,dilation
#     from scipy.ndimage import correlate
#     from scipy.ndimage import binary_fill_holes
#     
#     # 1/ Use phase congruency to detect edges
#     PC_NSCALE=4
#     PC_NORIENT=6
#     PC_MIN_WAVELENGTH=2
#     PC_MULT=2.5
#     PC_SIGMA_ONF=0.55
#     PC_K=2.0
#     PC_CUTOFF=0.3
#     PC_G=5
#     PC_NOISEMETHOD=-1
#     
#     def phasecong_Mm(roi):
#         r = phasecong(roi,PC_NSCALE,PC_NORIENT,PC_MIN_WAVELENGTH,PC_MULT,PC_SIGMA_ONF,PC_K,PC_CUTOFF,PC_G,PC_NOISEMETHOD)
#         # use the sum of the first two images returned by phasecong3:
#         # 1. The maximum moment of phase congruency covariance; indicates edges
#         # 2. The minimum moment of phase congruency covariance; indicates corners
#         M, m = r[0:2]
#         return M + m
#     
#     phase_edges = phasecong_Mm(img)
#     
#     
#     # 2/ Use hysteresis thresholding to extend edges using a combination of binary dilation and ordinary thresholding
#     def hysthresh(roi, T1, T2):
#         """
#         Hysteresis thresholding
#         
#         All pixels with values above T1 are marked as edges.
#         All pixels adjacent to points that have been marked as edges
#         and with values above T2 are also marked as edges. Eight-
#         connectivity is used.
#         
#         Adapted from Peter Kovesi
#         """
#         T2,T1 = sorted([T1,T2])
#         edges = roi > T1
#         EIGHT = np.ones((3,3)).astype(np.bool)
#         sum = 1
#         while sum > 0:
#             adj = (dilation(edges,EIGHT) & (roi > T2)) ^ edges
#             edges = edges | adj
#             sum = np.sum(adj)
#         return edges
#     
#     H = hysthresh(phase_edges, T1=0.2, T2=0.1)
#     
#     # trim pixels off border
#     H[H[:,1]==0,0]=0
#     H[H[:,-2]==0,-1]=0
#     H[0,H[1,:]==0]=0
#     H[-1,H[-2,:]==0]=0
#     
#     
#     # 3/ Add dark regions
#     DARK_THRESHOLD_ADJUSTMENT=0.65
#     
#     def dark_threshold(roi, adj=DARK_THRESHOLD_ADJUSTMENT):
#         samples = roi.flatten().astype(np.float32)
#         means, _ = kmeans2(samples,k=2)
#         thresh = np.mean(means)
#         return roi < thresh * adj
#     
#     dark = dark_threshold(img)
#     edges_and_dark = H | dark
#     
#     
#     # 4/ Closing and dilation to fill in holes and connect edges
#     closing_kernel = np.ones((5,5),dtype=np.bool)
#     msk_closed = closing(edges_and_dark, closing_kernel)
#     
#     dilation_kernel = np.array([[0, 0, 1, 0, 0],
#                     [0, 1, 1, 1, 0],
#                     [1, 1, 1, 1, 1],
#                     [0, 1, 1, 1, 0],
#                     [0, 0, 1, 0, 0]], dtype=np.bool)
#     msk_dilated = dilation(msk_closed,dilation_kernel)
#     
#     
#     # 5/ Perform morphological thinning of the segmentation using the algorithm of Guo and Hall (1989)
#     # Z. Guo and R. W. Hall, "Parallel thinning with two-subiteration algorithms," Comm. ACM, vol. 32, no. 3, pp. 359-373, 1989.
#     
#     # This optimized implementation is based on precomputed lookup tables, and so is rather opaque; see the paper for details on the algorithm
#     
#     G123_LUT = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 1,
#         0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0, 0,
#         1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0,
#         0, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 1,
#         0, 0, 0], dtype=np.bool)
#     
#     G123P_LUT = np.array([0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0,
#         1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0,
#         0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0,
#         1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 1,
#         0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
#         0, 0, 0], dtype=np.bool)
#     
#     def bwmorph_thin(roi, n_iter=1):
#         mask = np.array([[ 8,  4,  2],
#                         [16,  0,  1],
#                         [32, 64,128]],dtype=np.uint8)
#         skel = np.array(roi).astype(np.bool).astype(np.uint8)
#         for n in range(n_iter):
#             for lut in [G123_LUT, G123P_LUT]:
#                 N = correlate(skel, mask, mode='constant')
#                 D = np.take(lut,N)
#                 skel[D]=0
#         return skel.astype(np.bool)
#     
#     msk_thinned = bwmorph_thin(msk_dilated, 3)
#     
#     
#     # 6/ Fill any gaps that are enclosed in the segmentation
#     msk_filled = binary_fill_holes(msk_thinned)
#     
#     
#     # 7/ Keep only the largest connected region
#     labeled = measure.label(msk_filled)
#     regions = measure.regionprops(labeled)
#     if not regions:
#         return msk_filled
#     largest_region = max(regions, key=lambda r: _fast_particle_area(r))
#     mask = labeled == largest_region.label
#     
#     return mask


def _segment_particle(img: np.ndarray, logger: logging.Logger) -> np.ndarray:
    """
    Segment the largest particle from an image using edge detection and morphological operations.
    
    Args:
        image: Grayscale image as numpy array
        logger: Logger instance for logging warnings and info messages
        
    Returns:
        Binary mask of the largest particle, or None if no particle found
    """

    # Compute the background level as the median of the pixel values along the borders of the image
    borders = (img[0,:], img[-1,:], img[:,0], img[:,-1])
    bkg = np.median(np.concatenate(borders))

    # threshold the darker regions
    # TODO to handle strongly refringent objects, check of the center is lighter
    #      than the edges and, in that case, invert the image and re-threshold
    msk = img < bkg

    # Close the mask
    # dilate a bit, erode a bit, and close the remaining holes
    dilated = morphology.dilation(msk, morphology.disk(2))
    eroded = morphology.erosion(dilated, morphology.disk(2))
    filled = ndimage.binary_fill_holes(eroded)

    # Label connected regions
    labeled = measure.label(filled)
    if labeled.max() == 0:
        logger.warning("No particles found in image")
        return filled
    
    # Find the largest region
    regions = measure.regionprops(labeled)    
    largest_region = max(regions, key=lambda r: _fast_particle_area(r))
    
    # Create mask for largest region only
    mask = (labeled == largest_region.label)

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

            # Create the directory
            images_dir.mkdir(parents=True, exist_ok=True)

            image_count = 0
            rows = []
            for image in images:
                # TODO do this in parallel for all images?

                # Extract elements for the current image
                particle_id = image.get('particleId')                
                if particle_id is None:
                    logger.warning(f"Image missing 'particleId' in '{json_file.name}', skipping this image")
                    continue
                
                base64_data = image.get('base64')
                if base64_data is None:
                    logger.warning(f"Image {particle_id} missing 'base64' data in '{json_file.name}', skipping this image")
                    continue

                crop = image.get('cropRectangle')
                if crop is None:
                    logger.warning(f"Image {particle_id} missing 'cropRectangle' in '{json_file.name}', skipping this image")
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

                # clean the background and segment the particle
                img_no_bg = _clean_background(img, background_img, crop)
                img_mask = _segment_particle(img_no_bg, logger)
                
                # Add scale bar to the image
                # TODO get pixel size from the JSON file (instrument->measurementSettings->CytoSettings->iif->PixelSize)
                img = _add_scale_bar(img, pixel_size=0.5)
                # Add an empty area at the bottom of the mask to match the scale bar added to the image
                img_mask = np.concatenate((img_mask, np.zeros((31, img_mask.shape[1]), dtype=np.uint8)), axis=0)

                features = _extract_features(img_mask, img)
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

                rows += [row]

                # Write the image to a JPG file and the mask to a GIF file
                # (there is no point in saving the image as .png since the original data is already JPG compressed)
                output_file = images_dir / f"{particle_id}.jpg"
                with open(output_file, 'wb') as img_file:
                    iio.imwrite(img_file, img, format='jpg', quality=98)
                output_file = images_dir / f"{particle_id}.gif"
                with open(output_file, 'wb') as img_file:
                    img_mask = (img_mask * 255).astype(np.uint8)
                    iio.imwrite(img_file, img_mask, format='gif')
                
                image_count += 1
                    
            logger.info(f"  Extracted {image_count} images to\n  '{images_dir}'")
            total_images += image_count

             # Create features DataFrame and save to Parquet
            df = pd.DataFrame(rows)
            df = df.sort_values('object_id').reset_index(drop=True)
            df.to_parquet(features_file, index=False)
            
            logger.info(f"  Saved {df.shape[1]} properties to\n  '{features_file}'")
               
        except Exception as e:
            raiseCytoError(f"Error processing '{sample_id}': {e}", logger)
    
    logger.info(f"Total images extracted: {total_images}")
    log_command_success(logger, "Extract images")

# TODO add a way to post process the images to remove the background and crop them when they are full frames
# background = instrument['measurementSettings']['CytoSettings']['CytoSettings']['iif']['Background'].get('Data')
# background_data = base64.b64decode(background)
# output_file = Path(project) / "background.png"
# with open(output_file, 'wb') as img_file:
#     img_file.write(background_data)