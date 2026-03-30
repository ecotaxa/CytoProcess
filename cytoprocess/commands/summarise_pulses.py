from pathlib import Path
import click
import numpy as np
import pandas as pd
from numpy.polynomial.polynomial import Polynomial
from cytoprocess.logging import setup_logging, log_command_start, log_command_success
from cytoprocess.project import list_sample_assets, path_to_sample_asset
from cytoprocess.utils import (
    get_json_section,
    raiseCytoError
)
import imageio as iio
import os
from multiprocessing import Pool
import matplotlib
# Use non-interactive backend for plotting (no display needed)
matplotlib.use("Agg")
import matplotlib.pyplot as plt
# Set default plot style and size
plt.rcParams["figure.figsize"] = 7, 4
plt.rcParams["figure.autolayout"] = True
plt.rcParams["font.size"] = 8


def _normalise_pulse(values: list) -> np.ndarray:
    """
    Normalise a pulse vector to the range [0, 1].
    
    Args:
        values: List or array of numeric values
        
    Returns:
        Numpy array normalised to [0, 1], or zeros if max == min
    """
    arr = np.array(values, dtype=np.float32)
    min_val = arr.min()
    max_val = arr.max()
    
    if max_val == min_val:
        return np.zeros_like(arr)
    
    return (arr - min_val) / (max_val - min_val)


def _fit_polynomial(pulse: np.ndarray, n_poly: int) -> np.ndarray:
    """
    Fit a polynomial to a normalised pulse and return coefficients.
    
    Args:
        pulse: Normalised pulse values (numpy array)
        n_poly: Number of polynomial coefficients (degree = n_poly - 1)
        
    Returns:
        Numpy array of polynomial coefficients
    """
    x = np.linspace(0, 1, len(pulse))
    poly = Polynomial.fit(x=x, y=pulse, deg=n_poly - 1)
    return poly.convert().coef


def _process_single_particle(args):
    """
    Process a single particle to extract pulse shape features.
    
    Args:
        args: Tuple of (particle, sample_id, n_poly, pulses_img_dir, logger)
        
    Returns:
        Dictionary of features for one particle, or None if processing fails.
    """
    particle, sample_id, n_poly, pulses_img_dir, logger = args

    try:
        # Only process particles with images
        if not particle.get('hasImage', False):
            return None

        particle_idx = particle.get('particleId')
        if particle_idx is None:
            return None

        # get the pulse shapes
        pulse_shapes = particle.get('pulseShapes', [])
        
        if not pulse_shapes:
            logger.debug(f"No pulseShapes for particle {particle_idx} in sample '{sample_id}'")
            return None
        
        # Create a row for this particle
        row = {
            'sample_id': sample_id,
            'object_id': f"{sample_id}_{particle_idx}"
        }

        # Prepare storage for the normalised pulses and its plot
        pulses = {}
        pulses_img_dir.mkdir(parents=True, exist_ok=True)
        # Process each pulse shape (one per channel)
        for pulse_shape in pulse_shapes:
            description = pulse_shape.get('description')
            values = pulse_shape.get('values', [])
            
            if description is None or not values:
                continue
            
            # Normalise the pulse
            normalised = _normalise_pulse(values)
            
            # Fit polynomial and get coefficients
            coefficients = _fit_polynomial(normalised, n_poly)

            # Add normalised pulse to pulses dictionary
            pulses.update({description: normalised})

            # Add coefficients to row with appropriate column names
            for coef_idx, coef_val in enumerate(coefficients):
                col_name = f"object_{description}_p{coef_idx}"
                row[col_name] = coef_val
        
        if not pulses:
             return None

        # Plot pulses
        pulses = pd.DataFrame(pulses)
        pulses.plot().legend(bbox_to_anchor=(1.0, 0.35))
        # Improve plot aesthetics
        ax = plt.gca()
        ax.set_yticks([])                     # remove Y axis
        ax.set_ylabel("")                     #   normalised => only shape matters
        ax.get_legend().set_frame_on(False)   # remove legend box
        ax.spines['top'].set_visible(False)   # remove plot box
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        # Save the plot to disk
        img_path = pulses_img_dir / f"{particle_idx}_pulses.png"
        plt.savefig(img_path)
        plt.close()
        # Remove the alpha channel from the image to avoid issues with EcoTaxa
        # TODO revisit once https://github.com/ecotaxa/ecotaxa_back/pull/106 is merged
        img = iio.imread(img_path)
        if img.shape[2] == 4:
            img = img[:, :, :3]
            iio.imsave(img_path, img)
        # TODO reduce the size of plots (which are currently 5x larger than the actual cytosense image); either reduce the physical size or encode it differently
        
        return row
    except Exception as e:
        logger.error(f"Error processing particle {particle.get('particleId', 'N/A')} from sample {sample_id}: {e}")
        return None


def run(ctx: click.Context, project: Path, n_poly=10, force=False, max_cores=None):
    # Housekeeping for the command
    logger = setup_logging(command="summarise_pulses", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Summarising pulse shapes", project)
    if force:
        logger.debug("Force flag enabled: existing pulses summaries and plots will be overwritten")
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    logger.debug(f"Using {n_poly} polynomial coefficients")
    
    # Determine number of cores to use
    available_cores = os.cpu_count() or 1
    n_cores = max(1, available_cores - 1)
    if max_cores is not None:
        n_cores = min(n_cores, max_cores)
    logger.debug(f"Using {n_cores} core(s) for parallel processing")


    # Get JSON files from converted directory
    json_files = list_sample_assets(project, kind="json", logger=logger, ctx=ctx)
    if not json_files:
        return    
    logger.info(f"Processing {len(json_files)} .json file(s)")
    
    # Ensure output directories exist
    work_dir = project / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each JSON file and write one Parquet per sample
    for json_file in json_files:
        sample_id = json_file.parents[0].name
        output_file = project / path_to_sample_asset(sample_id, 'pulses_summaries', logger)
        pulses_plots_dir = project / path_to_sample_asset(sample_id, 'pulses_plots', logger)
        
        logger.info(f"'{sample_id}'")

        # Skip if output file exists and force is not set
        if output_file.exists() and pulses_plots_dir.exists() and not force:
            logger.info(f"  Skipping, outputs already exist (use --force to overwrite)")
            continue
        
        try:
            # Load the particles section of the json file
            particles_data = get_json_section(json_file, 'particles', logger)

            if particles_data is None or len(particles_data) == 0:
                logger.warning(f"No particles found in '{json_file.name}'")
                # Create an empty parquet file to avoid reprocessing this file in the future
                pd.DataFrame().to_parquet(output_file, index=False)
                continue
            
            logger.debug(f"Found {len(particles_data)} particles in '{json_file.name}'")
            
            # Prepare arguments for parallel processing
            args_list = [(p, sample_id, n_poly, pulses_plots_dir, logger) for p in particles_data]

            # Process particles in parallel
            logger.debug("Processing particles for pulse shape extraction")
            with Pool(processes=n_cores) as pool:
                results = pool.map(_process_single_particle, args_list)
            
            # Filter out None results
            rows = [r for r in results if r is not None]
            
            if not rows:
                logger.warning(f"No pulse data extracted from '{json_file.name}'")
                continue
            
            # Create DataFrame and save to Parquet
            df = pd.DataFrame(rows)
            df = df.sort_values('object_id').reset_index(drop=True)
            df.to_parquet(output_file, index=False)
            
            logger.info(f"  Saved {df.shape[0]} particles to\n  '{output_file}'\n  and pulse shape images to\n  '{pulses_plots_dir}'")
            
        except Exception as e:
            raiseCytoError(f"Error processing '{json_file.name}': {e}", logger)

    log_command_success(logger, "Summarise pulses")
