import pandas as pd
import zipfile
import numpy as np
from pathlib import Path
import imageio as iio
from cytoprocess.utils import ensure_project_dir, setup_logging, log_command_start, log_command_success, raiseCytoError


def _infer_ecotaxa_type(series):
    """
    Infer EcoTaxa column type from pandas Series.
        
    Args:
        series: pandas Series
        
    Returns:
        str: '[t]' for text columns and '[f]' for numeric columns.
    """
    # Check if column is numeric
    if pd.api.types.is_numeric_dtype(series):
        return '[f]'
    else:
        return '[t]'


def _add_scale_bar(input_path: Path, output_path: Path, pixel_size: float):
    """
    Add a scale bar at the bottom of the image
    
    Args:
        input_path: Path to the source JPG file
        output_path: Path to write the processed JPG file
        pixel_size: Size of one pixel in um
    """

    # Define a custom minimal 'font' for scale bar text
    f1 = np.asarray(
        [[1,1,0,1],
         [1,0,0,1],
         [1,1,0,1],
         [1,1,0,1],
         [1,1,0,1],
         [1,1,0,1],
         [1,1,0,1],
         [1,1,1,1],
         [1,1,1,1]])
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
    
    # Define scale bar sizes and corresponding text
    breaks_um = np.array([1, 10, 100])
    t1um  = np.concatenate((f1, fu, fm), axis=1)
    t10um = np.concatenate((f1, f0, fu, fm), axis=1)
    t100um = np.concatenate((f1, f0, f0, fu, fm), axis=1)
    breaks_text = [t1um, t10um, t100um]
    
    # Read the grayscale image
    img = iio.imread(input_path)
    img_width_px = img.shape[1]
    
    # Define how large the scale bar is for each physical size
    breaks_px = np.round(breaks_um / pixel_size)

    # Start the scale bar at these many pixels from the bottom left corner
    pad = 5

    # Find the most appropriate scale bar size given the width of the object
    break_idx = int(np.interp(img_width_px-pad, breaks_px, range(len(breaks_px))))
    
    # Pick the actual size and text we need for this size
    bar_width_px = int(breaks_px[break_idx])
    bar_text = breaks_text[break_idx]
    text_height_px,text_width_px = bar_text.shape

    # Define the width and height of the scale bar area
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
        
    # Write the processed image
    iio.imsave(output_path, img, quality=98)


def _list_samples(project: Path, sample_filter: str | None, logger) -> tuple[pd.DataFrame, list[str]]:
    """
    List samples to process from meta/samples.csv and optionally filter by sample_id.
    
    Args:
        project: Path to project directory
        sample_filter: Optional sample_id to filter to a single sample, from --sample
        logger: Logger instance
        
    Returns:
        List of sample_ids to process
    """
    samples_file = project / "meta" / "samples.csv"
    logger.debug(f"Checking '{samples_file}'")
    if not samples_file.exists():
        raiseCytoError(f"Missing samples metadata file, run `cytoprocess list {project}`.", logger)
    
    logger.debug(f"Reading reference samples list from '{samples_file}'")
    samples_df = pd.read_csv(samples_file, usecols=['sample_id'])
    samples = samples_df['sample_id'].unique().tolist()

    if sample_filter:
        if sample_filter not in samples:
            raiseCytoError(f"Sample '{sample_filter}' not found in '{samples_file}'.", logger)
        samples = [sample_filter]
        logger.info(f"Preparing EcoTaxa file for sample: '{sample_filter}'")
    
    else:
        logger.info(f"Preparing EcoTaxa file for {len(samples)} sample(s)")
    
    return samples


def _detect_extra_samples(project: Path, samples: list[str], logger) -> None:
    """
    Detect and warn about samples in work/ that are not listed in samples.csv.
    
    Args:
        project: Path to project directory
        samples: List of sample_ids existing in samples.csv
        logger: Logger instance
    """
    work_dir = project / "work"

    instrument_meta_file = work_dir / "sample_metadata_from_instrument.parquet"
    if instrument_meta_file.exists():
        logger.debug(f"Reading instrument metadata from '{instrument_meta_file}'")
        instrument_meta_df = pd.read_parquet(instrument_meta_file, columns=['sample_id'])
        work_samples = set(instrument_meta_df['sample_id'].tolist())
    else:
        work_samples = set()
    
    for pattern, suffix in [("*_cytometric_features.parquet", "_cytometric_features"),
                            ("*_pulses.parquet", "_pulses"),
                            ("*_image_features.parquet", "_image_features")]:
        for file in sorted(work_dir.glob(pattern)):
            sample_id = file.stem.replace(suffix, "")
            work_samples.add(sample_id)
    
    extra_samples = work_samples - set(samples)
    if extra_samples:
        logger.warning(f"NB: Detected {len(extra_samples)} sample(s) in 'work/' not listed in 'meta/samples.csv': {sorted(extra_samples)}; you should re-run `cytoprocess list {project}`.")


def _ensure_sample_data(project: Path, samples: list[str], logger) -> None:
    """
    Validate all required input data/files exist for requested samples.
    
    Args:
        project: Path to project directory
        samples: List of sample_ids to validate
        logger: Logger instance
        
    Raises:
        CytoError if any required files are missing
    """
    logger.debug("Verifying required input files for all requested samples")
    
    work_dir = project / "work"
    instrument_meta_file = work_dir / "sample_metadata_from_instrument.parquet"
    
    if not instrument_meta_file.exists():
        raiseCytoError(f"Missing metadata from the instrument, run `cytoprocess extract_meta {project}`.", logger)

    logger.debug(f"Reading instrument metadata from '{instrument_meta_file}'")
    instrument_meta_df = pd.read_parquet(instrument_meta_file, columns=['sample_id'])
    
    at_least_one_missing = False
    for sample_id in samples:
        if sample_id not in instrument_meta_df['sample_id'].values:
            logger.warning(f"Missing metadata from the instrument, run `cytoprocess --sample '{sample_id}' extract_meta {project}`")
            at_least_one_missing = True

        cytometric_file = work_dir / f"{sample_id}_cytometric_features.parquet"
        if not cytometric_file.exists():
            logger.warning(f"Missing cytometric features, run `cytoprocess --sample '{sample_id}' extract_features {project}`")
            at_least_one_missing = True

        pulses_file = work_dir / f"{sample_id}_pulses.parquet"
        if not pulses_file.exists():
            logger.warning(f"Missing pulses summary, run `cytoprocess --sample '{sample_id}' summarise_pulses {project}`")
            at_least_one_missing = True

        images_dir = project / "images" / sample_id
        if not images_dir.exists():
            logger.warning(f"Images not found, run `cytoprocess --sample '{sample_id}' extract_images {project}`")
            at_least_one_missing = True
        
        image_features_file = work_dir / f"{sample_id}_image_features.parquet"
        if not image_features_file.exists():
            logger.warning(f"Missing image features, run `cytoprocess --sample '{sample_id}' compute_features {project}`")
            at_least_one_missing = True

    if at_least_one_missing:
        raiseCytoError("Missing input for some samples. Please run the required extraction steps before preparing EcoTaxa files.", logger)
    

def _merge_sample_data(project: Path, sample_id: str, samples_meta_df: pd.DataFrame, 
                       instrument_meta_df: pd.DataFrame, logger) -> tuple[pd.DataFrame, float]:
    """
    Merge all data sources for a sample into a single DataFrame.
    
    Args:
        project: Path to project directory
        sample_id: The sample identifier
        samples_meta_df: DataFrame with custom sample-level metadata
        instrument_meta_df: DataFrame with sample-level metadata from the instrument
        logger: Logger instance
        
    Returns:
        Tuple of (merged DataFrame, pixel_size in mm)
    """
    work_dir = project / "work"
    
    # Get sample-level metadata for this sample
    sample_meta = samples_meta_df[samples_meta_df['sample_id'] == sample_id]
    instrument_meta = instrument_meta_df[instrument_meta_df['sample_id'] == sample_id]
    
    # Read object metadata files for this sample
    cytometric_df = pd.read_parquet(work_dir / f"{sample_id}_cytometric_features.parquet")
    image_features_df = pd.read_parquet(work_dir / f"{sample_id}_image_features.parquet")
    pulses_df = pd.read_parquet(work_dir / f"{sample_id}_pulses.parquet")

    # Extract pixel size from our custom column and remove it
    pixel_size = np.float32(instrument_meta.iloc[0]['__pixel_size__'])
    instrument_meta = instrument_meta.drop(columns=['__pixel_size__'])

    # Merge all data
    df = cytometric_df.merge(image_features_df, on=['sample_id', 'object_id'], how='left')
    df = df.merge(pulses_df, on=['sample_id', 'object_id'], how='left')
    df = df.merge(sample_meta, on=['sample_id'], how='left')
    df = df.merge(instrument_meta, on=['sample_id'], how='left')

    # Define process_id as acq_id
    df['process_id'] = df['acq_id']

    logger.debug(f"Found {len(df)} objects for sample '{sample_id}'")
    
    return df, pixel_size


def _prepare_ecotaxa_tsv(df: pd.DataFrame, tsv_file: Path, logger) -> pd.DataFrame:
    """
    Prepare and write EcoTaxa TSV file with column type inference.
    
    Enforces EcoTaxa column limits and writes TSV with type indicator row.
    
    Args:
        df: Merged DataFrame with all sample data
        tsv_file: Path to output TSV file
        logger: Logger instance
        
    Returns:
        The sorted DataFrame used for the TSV (for further processing)
    """
    # Get the sample_id value from the assembled data (same for all rows)
    sample_id = df["sample_id"].iloc[0]
    
    # Add image filename based on object_id (this is the actual image)
    df['img_file_name'] = df['object_id'].str.replace(f"{sample_id}_", "", n=1) + ".jpg"
    
    # Add img_rank (0-based index for multiple images per object)
    df['img_rank'] = 0

    # Reorder columns to put all *_id columns first, for cleanness
    id_cols = [c for c in df.columns if c.endswith('_id')]
    other_cols = [c for c in df.columns if not c.endswith('_id')]
    df = df[id_cols + other_cols]

    # Count columns per prefix and enforce EcoTaxa limits
    cols = df.columns.tolist()
    img_cols = [c for c in cols if c.startswith('img_')]
    object_cols = [c for c in cols if c.startswith('object_')]
    process_cols = [c for c in cols if c.startswith('process_')]
    acq_cols = [c for c in cols if c.startswith('acq_')]
    sample_cols = [c for c in cols if c.startswith('sample_')]

    # Limit object metadata columns to 500
    # NB: since object_id does not count as metadata, this means a maximum of 501 columns
    # TODO actually object_lon, lat etc. do not count either so we could add more columns
    if len(object_cols) > 501:
        logger.warning(f"Sample '{sample_id}' has {len(object_cols)-1} object metadata columns, truncating to 500 (EcoTaxa limit)")
        object_cols = object_cols[:501]
    # Limit sample, process, and acq columns
    if len(process_cols) > 31:
        logger.warning(f"Sample '{sample_id}' has {len(process_cols)-1} process metadata columns, truncating to 30 (EcoTaxa limit)")
        process_cols = process_cols[:31]
    if len(acq_cols) > 31:
        logger.warning(f"Sample '{sample_id}' has {len(acq_cols)-1} acq metadata columns, truncating to 30 (EcoTaxa limit)")
        acq_cols = acq_cols[:31]
    if len(sample_cols) > 61:
        logger.warning(f"Sample '{sample_id}' has {len(sample_cols)-1} sample metadata columns, truncating to 60 (EcoTaxa limit)")
        sample_cols = sample_cols[:61]

    # Order columns for cleanness
    ordered_cols = img_cols + object_cols + process_cols + acq_cols + sample_cols
    sorted_df = df[ordered_cols]
    
    # Create type indicators row
    type_row = {col: _infer_ecotaxa_type(sorted_df[col]) for col in sorted_df.columns}
    
    # Create the EcoTaxa .tsv file
    with open(tsv_file, 'w') as f:
        f.write('\t'.join(sorted_df.columns) + '\n')
        f.write('\t'.join([type_row[col] for col in sorted_df.columns]) + '\n')
        sorted_df.to_csv(f, sep='\t', index=False, header=False)
    
    logger.debug(f"Saved {sorted_df.shape[1]} fields for {sorted_df.shape[0]} objects to '{tsv_file}'")
    return sorted_df


def _create_ecotaxa_zip(tsv_file: Path, zip_file: Path, images_dir: Path, 
                        ecotaxa_dir: Path, pixel_size: float, logger) -> None:
    """
    Create EcoTaxa ZIP file containing TSV and processed images with scale bars.
    
    Cleans up temporary files (TSV and processed images) after creating the ZIP.
    
    Args:
        tsv_file: Path to the TSV file to include
        zip_file: Path to output ZIP file
        images_dir: Directory containing source PNG images
        ecotaxa_dir: Directory for temporary processed images
        pixel_size: Pixel size in mm (for scale bar)
        logger: Logger instance
    """
    image_files = list(images_dir.glob("*.jpg"))
    processed_images = []
    
    with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add the TSV file
        zf.write(tsv_file, tsv_file.name)
        
        # Process and add all images from the sample's images directory
        logger.debug(f"Processing and adding {len(image_files)} images to zip file")
        
        for image_file in image_files:
            # Process image: add scale bar at bottom
            processed_path = ecotaxa_dir / image_file.name
            _add_scale_bar(image_file, processed_path, pixel_size)
            processed_images.append(processed_path)
            
            # Add to zip
            zf.write(processed_path, processed_path.name)
    
    logger.debug(f"Created zip file '{zip_file}' with {len(image_files)} images")

    # Remove the TSV file after adding it to the zip
    logger.debug(f"Removing temporary TSV file '{tsv_file}'")
    tsv_file.unlink()
    
    # Remove processed images after adding them to the zip
    logger.debug(f"Removing {len(processed_images)} temporary processed images")
    for processed_path in processed_images:
        processed_path.unlink()


def run(ctx, project, force=False, only_tsv=False):
    """Prepare EcoTaxa TSV/ZIP files for samples."""
    logger = setup_logging(command="prepare", project=project, debug=ctx.obj["debug"])
    
    log_command_start(logger, "Preparing EcoTaxa files", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    if only_tsv:
        logger.debug("Only creating TSV files (--only-tsv flag enabled)")

    project = Path(project)
    work_dir = project / "work"
    sample_filter = getattr(ctx, "obj", {}).get("sample")

    # List samples to process from meta/samples.csv
    samples = _list_samples(project, sample_filter, logger)        

    # Warn about extra samples in work/, if we are processing all samples
    # When --sample is used, work/ likely contains other samples so we skip this check
    if not sample_filter:
        _detect_extra_samples(project, samples, logger)

    # Check that all required input data/files exist for the target samples
    _ensure_sample_data(project, samples, logger)

    # Prepare storage
    ecotaxa_dir = ensure_project_dir(project, "ecotaxa")

    # Read sample-level metadata and instrument metadata
    # We do not need checks here these the existence of these files is already verified 
    samples_meta_df = pd.read_csv(project / "meta" / "samples.csv")
    instrument_meta_df = pd.read_parquet(work_dir / "sample_metadata_from_instrument.parquet")

    for sample_id in samples:
        logger.info(f"'{sample_id}'")

        tsv_file = ecotaxa_dir / f"ecotaxa_{sample_id}.tsv"
        zip_file = ecotaxa_dir / f"ecotaxa_{sample_id}.zip"

        # Skip if output file exists and force is not set
        if (tsv_file.exists() and only_tsv and not force) or \
           (zip_file.exists() and not only_tsv and not force):
            logger.info(f"  Skipping, ecotaxa_*." + ("tsv" if only_tsv else "zip") + " file already exists (use --force to overwrite)")
            continue
        
        logger.info(f"  Collating '{tsv_file}'")

        # Merge all data for this sample
        df, pixel_size = _merge_sample_data(project, sample_id, samples_meta_df, instrument_meta_df,   logger)

        # Prepare TSV file
        _prepare_ecotaxa_tsv(df, tsv_file, logger)
        
        if only_tsv:
            logger.debug("Skipping zip creation, only TSV file requested (--only-tsv)")
            continue

        # Create zip file
        logger.info(f"  Assembling '{zip_file}'")
        images_dir = project / "images" / sample_id
        _create_ecotaxa_zip(tsv_file, zip_file, images_dir, ecotaxa_dir, pixel_size, logger)
        # TODO move image processing in extract_images

    log_command_success(logger, "Prepare EcoTaxa files")
