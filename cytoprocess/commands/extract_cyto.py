import yaml
import pandas as pd
from pathlib import Path
from cytoprocess.utils import get_sample_files, ensure_project_dir, get_json_section, setup_logging, log_command_start, log_command_success, raiseCytoError
import ijson
import numpy as np

def _get_parameters_structure(parameters):
    """
    Extract all available paths from a particle's parameters list.
    
    Parameters is a list of dicts, each identified by its 'description' field.
    This function generates paths in the format "description.key" for all
    available keys.
    
    Args:
        parameters: List of parameter dicts, each with a 'description' key
        
    Returns:
        List of paths like ['FWS.length', 'FWS.total', 'Sidewards Scatter.length', ...]
        
    Examples:
        >>> params = [
        ...     {'description': 'FWS', 'length': 0.98, 'total': 40621.9},
        ...     {'description': 'Sidewards Scatter', 'length': 10.77, 'total': 1276.4}
        ... ]
        >>> paths = _get_parameters_structure(params)
        >>> 'FWS.length' in paths
        True
    """
    paths = []
    
    for param_dict in parameters:
        if not isinstance(param_dict, dict):
            continue
            
        description = param_dict.get('description')
        if description is None:
            continue
            
        # Add paths for all keys except 'description' itself
        for key in param_dict.keys():
            if key != 'description':
                paths.append(f"{description}.{key}")
    
    return paths


def _get_parameter_value(parameters, path):
    """
    Retrieve a value from a particle's parameters list given a path.
    
    The path format is "description.key" where description identifies the
    parameter dict and key is the field to retrieve.
    
    Args:
        parameters: List of parameter dicts, each with a 'description' key
        path: Path string (e.g., "FWS.length" or "Sidewards Scatter.total")
        
    Returns:
        The value at the given path, or None if not found.
        
    Examples:
        >>> params = [
        ...     {'description': 'FWS', 'length': 0.98, 'total': 40621.9},
        ...     {'description': 'Sidewards Scatter', 'length': 10.77}
        ... ]
        >>> _get_parameter_value(params, "FWS.length")
        0.98
        >>> _get_parameter_value(params, "Sidewards Scatter.length")
        10.77
    """
    # Split path into description and key
    parts = path.split('.', 1)
    if len(parts) != 2:
        return None
    
    description, key = parts
    
    # Find the parameter dict with matching description
    for param_dict in parameters:
        if not isinstance(param_dict, dict):
            continue
        if param_dict.get('description') == description:
            return param_dict.get(key)
    
    return None


def run(ctx, project, list_keys=False, force=False):
    logger = setup_logging(command="extract_cyto", project=project, debug=ctx.obj["debug"])

    log_command_start(logger, "Extracting cytometric features", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    
    # Get JSON files from converted directory
    json_files = get_sample_files(project, logger, kind="json", ctx=ctx)
    if not json_files:
        return
    
    logger.info(f"Processing {len(json_files)} .json file(s)")
    
    if list_keys:
        # If the --list argument is provided, extract available parameter paths
        # from the first particle of each JSON file
        
        paths = []
        for json_file in json_files:
            logger.debug(f"Listing parameter paths from {json_file.name}")
            try:
                with open(json_file, 'rb') as f:
                    # Use ijson to navigate to the particles array and get the first item
                    parser = ijson.items(f, 'particles.item')
                    first_particle = next(parser, None)
                    
                if first_particle is None:
                       logger.warning(f"No particles found in '{json_file.name}'")
                       continue
                    
                parameters = first_particle.get('parameters', [])
                
                if parameters is None or len(parameters) == 0:
                    logger.warning(f"No parameters found in first particle of '{json_file.name}'")
                    continue
                                
                paths.extend(_get_parameters_structure(parameters))
                                
            except Exception as e:
                raiseCytoError(f"Error reading '{json_file.name}': {e}", logger)
        
        if not paths:
            raiseCytoError("No parameter paths found in any .json file", logger)
        
        # Deduplicate and sort
        paths = sorted(set(paths))
        logger.info(f"Found {len(paths)} parameter paths")
        
        # Write paths to file
        meta_dir = ensure_project_dir(project, "meta")
        paths_file = meta_dir / "available_cytometry_features.txt"
        with open(paths_file, 'w') as f:
            for path in paths:
                f.write(f"{path}\n")
        
        logger.info(f"Available cytometric features written to '{paths_file}'. Use them in the object section of the config/config.yaml file to define cytometric feature extraction.")
    
    else:
        # Normal operation: extract cytometric features based on config.yaml

        config_file = Path(project) / "config" / "config.yaml"
        logger.info(f"Read selected cytometric features list from '{config_file}'")
        
        if not config_file.exists():
            raiseCytoError(f"Configuration file not found: '{config_file}', run 'cytoprocess create {project}' again.", logger)
        
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Get the 'object' section from config
        object_config = config.get('object')
        if not object_config or not isinstance(object_config, dict):
            raiseCytoError(f"No 'object' section found in '{config_file}'. Configuration file must contain an 'object' section with cytometric feature mappings.", logger)
        
        logger.debug(f"Found {len(object_config)} mappings in 'object' section")
        
        # Ensure work directory exists, to store output files
        work_dir = ensure_project_dir(project, "work")
        
        # Process each JSON file and write one Parquet per sample
        for json_file in json_files:
            sample_id = json_file.stem
            output_file = work_dir / f"{sample_id}_cytometric_features.parquet"

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

                # Use the sets definition to compute imaging ratio and imaged/analysed volume
                # This creates one acquisition per set and we later link each particle to its acquisition
                sets = get_json_section(json_file, 'set_information', logger)
                # default acquisition
                set_stats_df = pd.DataFrame({'name': sample_id,
                                             'acq_imaging_ratio': 0,
                                             'acq_imaged_volume_uL': 0,
                                             'acq_analysed_volume_uL': 0}, index=[0])
                if sets is None:
                    logger.warning(f"No set information found in '{json_file.name}'; CytoProcess will not be able to compute subsampling factors.")
                else:
                    # Keep only sets with images and a valid imaged_volume
                    sets_stats = [s for s in sets.get("statistics", []) if
                                  s.get("images", 0) > 0 and
                                  not s.get("imaged_volume") == 'NaN']
                    # Compute relevant quantifies
                    for s in sets_stats:
                        imaging_ratio = s['images'] / s['count']
                        analysed_volume = s['imaged_volume'] / imaging_ratio
                        sets_stats_df = pd.concat([
                            set_stats_df,
                            pd.DataFrame({'name': s['name'],
                                          'acq_imaging_ratio': imaging_ratio,
                                          'acq_imaged_volume_uL': s['imaged_volume'],
                                          'acq_analysed_volume_uL': analysed_volume}, index=[0])])
                # Rename 'name' to its actual meaning
                sets_stats_df = sets_stats_df.rename(columns={'name': 'acq_id'})

                # Prepare data structure: list of dicts, one per particle
                rows = []
                
                # log cases with multiple regions, which should not happen but we want to be aware of it if it does
                multiple_regions = []

                # Process each particle
                for particle in particles_data:
                    # Only process particles with images
                    if not particle.get('hasImage', False):
                        continue
                    # TODO add an --all option to also extract particles without images, which can be useful for some applications (e.g. classification from flow cytometry data only)

                    particle_idx = particle.get('particleId')

                    # Get all its features
                    parameters = particle.get('parameters', [])
                    
                    if not parameters:
                        logger.debug(f"No parameters for particle {particle_idx} in '{json_file.name}'")
                        continue
                    
                    # Create a row for this particle
                    row = {
                        'sample_id': sample_id,
                        'object_id': f"{sample_id}_{particle_idx}",
                    }

                    # Extract the set the particle is in based on its 'region' property
                    acq_id = 'Other imaged particles'
                    region = particle.get('region', [])
                    if region and len(region) > 0:
                        # Remove the fact that a given particle is in 'All Imaged Particles' = we don't care
                        region = [r for r in region if r != 'All Imaged Particles']
                        if len(region) > 0:
                            acq_id = region[0]
                        if len(region) > 1:
                            multiple_regions.append(tuple(region))
                            
                    row['acq_id'] = acq_id
                    
                    # Extract each mapped value
                    for json_path, column_name in object_config.items():
                        # Prepend 'object_' to column name for EcoTaxa compatibility
                        full_column_name = f"object_{column_name}"
                        
                        # Get the value from the parameters
                        value = _get_parameter_value(parameters, json_path)
                        
                        if value is None:
                            logger.debug(f"Path '{json_path}' not found in particle {particle_idx} of '{json_file.name}'")
                        if value == 'NaN':
                            logger.debug(f"Path '{json_path}' has value 'NaN' for particle {particle_idx} of '{json_file.name}'")
                            value = np.nan
                        
                        row[full_column_name] = value
                    
                    rows.append(row)
                
                if not rows:
                    logger.warning(f"No particle data extracted from '{json_file.name}'")
                    continue

                # Warn about particles which were in multiple sets
                if multiple_regions:
                    # Count how many particles were in which combination of sets
                    unique_tuples, counts = np.unique(multiple_regions, axis=0, return_counts=True)
                    multiple_regions_counts = dict(zip(map(lambda x: ', '.join(x), unique_tuples), [int(c) for c in counts]))
                    logger.warning(f"Some particles were in several sets: {multiple_regions_counts}; only the first set has been considered for those particles.")

                # Create DataFrame and save to Parquet
                df = pd.DataFrame(rows)
                # add acquisition stats
                df = df.merge(sets_stats_df, how='left', on='acq_id')
                df.to_parquet(output_file, index=False)
                
                logger.info(f"  Saved {df.shape[1]} properties for {df.shape[0]} particles to\n  '{output_file}'")
                
            except Exception as e:
                raiseCytoError(f"Error processing '{json_file.name}': {e}", logger)

    log_command_success(logger, "Extract cytometric features")
