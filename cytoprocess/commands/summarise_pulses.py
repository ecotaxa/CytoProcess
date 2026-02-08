import logging
import numpy as np
import pandas as pd
from numpy.polynomial.polynomial import Polynomial
from cytoprocess.utils import get_sample_files, ensure_project_dir, get_json_section, setup_logging, log_command_start, log_command_success, raiseCytoError


def _normalise_pulse(values):
    """
    Normalise a pulse vector to the range [0, 1].
    
    Args:
        values: List or array of numeric values
        
    Returns:
        Numpy array normalised to [0, 1], or zeros if max == min
    """
    arr = np.array([float(v) for v in values])
    min_val = arr.min()
    max_val = arr.max()
    
    if max_val == min_val:
        return np.zeros_like(arr)
    
    return (arr - min_val) / (max_val - min_val)


def _fit_polynomial(pulse, n_poly):
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


def run(ctx, project, n_poly=10, force=False):
    logger = setup_logging(command="summarise_pulses", project=project, debug=ctx.obj["debug"])

    log_command_start(logger, "Summarising pulse shapes", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    logger.debug(f"Using {n_poly} polynomial coefficients")
    
    # Get JSON files from converted directory
    json_files = get_sample_files(project, logger, kind="json", ctx=ctx)
    if not json_files:
        return
    
    logger.info(f"Processing {len(json_files)} .json file(s)")
    
    # Ensure work directory exists
    work_dir = ensure_project_dir(project, "work")
    
    # Process each JSON file and write one Parquet per sample
    for json_file in json_files:
        sample_id = json_file.stem
        output_file = work_dir / f"{sample_id}_pulses.parquet"
        
        logger.info(f"'{json_file.stem}'")

        # Skip if output file exists and force is not set
        if output_file.exists() and not force:
            logger.info(f"  Skipping, output file already exists (use --force to overwrite)")
            continue
        
        try:
            # Load the particles section of the json file
            particles_data = get_json_section(json_file, 'particles', logger)

            if particles_data is None or len(particles_data) == 0:
                logger.warning(f"No particles found in '{json_file.name}'")
                continue
            
            logger.debug(f"Found {len(particles_data)} particles in '{json_file.name}'")
            
            # Prepare data structure: list of dicts, one per particle
            rows = []
            
            # Process each particle
            logger.debug("Processing particles for pulse shape extraction")
            for particle in particles_data:                
                    # Only process particles with images
                if not particle.get('hasImage', False):
                    continue

                particle_idx = particle.get('particleId')

                # get the pulse shapes
                pulse_shapes = particle.get('pulseShapes', [])
                
                if not pulse_shapes:
                    logger.debug(f"No pulseShapes for particle {particle_idx} in '{json_file.name}'")
                    continue
                
                # Create a row for this particle
                row = {
                    'sample_id': sample_id,
                    'object_id': f"{sample_id}_{particle_idx}"
                }
                
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
                    
                    # Add coefficients to row with appropriate column names
                    for coef_idx, coef_val in enumerate(coefficients):
                        col_name = f"object_{description}_p{coef_idx}"
                        row[col_name] = coef_val
                
                rows.append(row)
            
            if not rows:
                logger.warning(f"No pulse data extracted from '{json_file.name}'")
                continue
            
            # Create DataFrame and save to Parquet
            df = pd.DataFrame(rows)
            df = df.sort_values('object_id').reset_index(drop=True)
            df.to_parquet(output_file, index=False)
            
            logger.info(f"  Saved {df.shape[0]} particles to\n  '{output_file}'")
            
        except Exception as e:
            raiseCytoError(f"Error processing '{json_file.name}': {e}", logger)

    log_command_success(logger, "Summarise pulses")
