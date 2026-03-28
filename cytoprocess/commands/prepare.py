import pandas as pd
import zipfile
import os
from multiprocessing import Pool
import numpy as np
from pathlib import Path
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
            logger.warning(f"Missing cytometric features, run `cytoprocess --sample '{sample_id}' extract_cyto {project}`")
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

    # If the cytometric dataframe is empty, it means there were no particles detected for this sample,
    # so we can skip the rest of the processing and return empty results
    if cytometric_df.empty:
        return pd.DataFrame(), 0.0

    # Extract pixel size from our custom column and remove it
    pixel_size = instrument_meta.iloc[0]['__pixel_size__']
    instrument_meta = instrument_meta.drop(columns=['__pixel_size__'])

    # Merge all data
    df = cytometric_df.merge(image_features_df, on=['sample_id', 'object_id'], how='left')
    df = df.merge(pulses_df, on=['sample_id', 'object_id'], how='left')
    df = df.merge(sample_meta, on=['sample_id'], how='left')
    df = df.merge(instrument_meta, on=['sample_id'], how='left')

    # Prepend sample id to acq_id to avoid conflicts
    # (and name process id the same)
    df['acq_id'] = df['sample_id'] + "_" + df['acq_id']
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
    df = df[ordered_cols]
    
    # Create type indicators row
    type_row = {col: _infer_ecotaxa_type(df[col]) for col in df.columns}

    # Duplicate the DataFrame to reference pulse shape images
    # (they have the same id but are stored as PNG files)
    df_png = df.copy()
    df_png['img_file_name'] = df_png['img_file_name'].str.replace('.jpg', '.png', regex=False)
    df_png['img_rank'] = 1

    # Combine the two DataFrames
    df = pd.concat([df, df_png], ignore_index=True)
    # Sort by object_id for consistent ordering
    df = df.sort_values(by="object_id").reset_index(drop=True)
    
    # Create the EcoTaxa .tsv file
    with open(tsv_file, 'w') as f:
        f.write('\t'.join(df.columns) + '\n')
        f.write('\t'.join([type_row[col] for col in df.columns]) + '\n')
        df.to_csv(f, sep='\t', index=False, header=False)
    
    logger.debug(f"Saved {df.shape[1]} fields for {int(df.shape[0]/2)} objects to '{tsv_file}'")
    return df


def _create_ecotaxa_zip(tsv_file: Path, zip_file: Path, images_dir: Path, pulses_dir: Path,
                        ecotaxa_dir: Path, pixel_size: float, max_cores: int, logger) -> None:
    """
    Create EcoTaxa ZIP file containing TSV and processed images with scale bars.
    
    Cleans up temporary files (TSV and processed images) after creating the ZIP.
    
    Args:
        tsv_file: Path to the TSV file to include
        zip_file: Path to output ZIP file
        images_dir: Directory containing source PNG images
        ecotaxa_dir: Directory for temporary processed images
        pixel_size: Pixel size in mm (for scale bar)
        max_cores: Maximum number of cores to use
        logger: Logger instance
    """
    pulses_files = list(pulses_dir.glob("*.png"))
    image_files = list(images_dir.glob("*.jpg"))
    processed_images = []
    
    logger.debug(f"Processing {len(image_files)} images to zip file")
    # Determine number of cores to use
    available_cores = os.cpu_count() or 1
    n_cores = max(1, available_cores - 1)
    if max_cores is not None:
        n_cores = min(n_cores, max_cores)
    logger.debug(f"Using {n_cores} core(s) for parallel processing")
    # TODO wrap this into a function and reuse it everywhere we do parallel processing

    # args = [(image_file, ecotaxa_dir / image_file.name, pixel_size) for image_file in image_files]
    # with Pool(processes=n_cores) as pool:
    #     processed_images = pool.map(_add_scale_bar_multiprocessing, args)

    logger.debug(f"Creating zip file '{zip_file}'")
    with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add the TSV file
        zf.write(tsv_file, tsv_file.name)

        # Add processed images to zip
        for processed_image in processed_images:
            zf.write(processed_image, processed_image.name)

        # Add all pulses files to the zip
        logger.debug(f"Adding {len(pulses_files)} pulse plot images to zip file")
        for pulse_file in pulses_files:
            zf.write(pulse_file, pulse_file.name)
    
    logger.debug(f"Created zip file '{zip_file}' with {len(image_files)} images")

    # Remove the TSV file after adding it to the zip
    logger.debug(f"Removing temporary TSV file '{tsv_file}'")
    tsv_file.unlink()
    
    # Remove processed images after adding them to the zip
    logger.debug(f"Removing {len(processed_images)} temporary processed images")
    for processed_image in processed_images:
        processed_image.unlink()


def run(ctx, project, force=False, only_tsv=False, max_cores=None):
    # Housekeeping for the command
    logger = setup_logging(command="prepare", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Preparing EcoTaxa files", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    if force:
        logger.debug("Force flag enabled, existing ecotaxa files will be overwritten")
    if only_tsv:
        logger.debug("only-tsv flag enabled: only creating TSV files, not ZIP files with images")


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
        df, pixel_size = _merge_sample_data(project, sample_id, samples_meta_df, instrument_meta_df, logger)
        # If the merged dataframe is empty, skip to the next sample
        if df.empty:
            logger.warning(f"No imaged particles for sample '{sample_id}', skipping.")
            continue

        # Prepare TSV file
        _prepare_ecotaxa_tsv(df, tsv_file, logger)
        
        if only_tsv:
            logger.debug("Skipping zip creation, only TSV file requested (--only-tsv)")
            continue

        # Create zip file
        logger.info(f"  Assembling '{zip_file}'")
        images_dir = project / "images" / sample_id
        pulses_dir = project / "pulses" / sample_id
        _create_ecotaxa_zip(tsv_file, zip_file, images_dir, pulses_dir, ecotaxa_dir, pixel_size, max_cores, logger)
        # TODO move image processing in extract_images

    log_command_success(logger, "Prepare EcoTaxa files")
