import logging
import ijson
import yaml
import pandas as pd
from pathlib import Path
from cytoprocess.utils import get_sample_files, ensure_project_dir, get_json_section, setup_logging, log_command_start, log_command_success, raiseCytoError


def _get_json_structure(json_data, prefix=""):
    """
    Recursively extract all keys from a JSON object and return them as full paths.
    
    Args:
        json_data: Parsed JSON data (dict, list, or primitive)
        prefix: The current path prefix (used for recursion)
        
    Returns:
        List of full paths to all keys in the JSON structure.
        Paths are separated by dots (e.g., "data.user.name")
        List items are indicated with [] notation (e.g., "items[].name")
        
    Examples:
        >>> data = {"user": {"name": "John", "age": 30}, "active": True}
        >>> paths = _get_json_structure(data)
        >>> paths
        ['user', 'user.name', 'user.age', 'active']
        
        >>> data = {"items": [{"id": 1, "name": "Item1"}, {"id": 2}], "count": 2}
        >>> paths = _get_json_structure(data)
        >>> paths
        ['items[]', 'items[].id', 'items[].name', 'count']
    """
    paths = []
    
    if isinstance(json_data, dict):
        for key, value in json_data.items():
            # Build the full path
            current_path = f"{prefix}.{key}" if prefix else key
            
            # Recursively get paths from nested structures
            if isinstance(value, dict):
                # For dicts, add the key and recurse
                paths.append(current_path)
                paths.extend(_get_json_structure(value, current_path))
            elif isinstance(value, list) and value:
                # For lists, add the key[] notation
                list_path = f"{current_path}[]"
                paths.append(list_path)
                # If it's a list of dicts, extract structure from first item
                # (this assummes that all items have the same structure)
                if isinstance(value[0], dict):
                    paths.extend(_get_json_structure(value[0], list_path))
            else:
                # For non-dict, non-list values, just add the key
                paths.append(current_path)
    
    return paths


def _get_json_item(json_data, path):
    """
    Retrieve value(s) from a JSON object given a path with dot notation.
    
    Handles paths that include [] notation for list items.
    When a list is encountered, all matching values are collected and
    concatenated with spaces.
    
    Args:
        json_data: Parsed JSON data (dict)
        path: Path string (e.g., "user.name" or "items[].id")
        
    Returns:
        The value at the given path. For list items, returns a space-separated
        string of all matching values. Returns None if path not found.
        
    Examples:
        >>> data = {"user": {"name": "John"}}
        >>> _get_json_item(data, "user.name")
        'John'
        
        >>> data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
        >>> _get_json_item(data, "items[].id")
        '1 2 3'
    """
    path_parts = path.split('.')
    current = json_data
    values = []
    
    for part in path_parts:
        if current is None:
            return None
            
        # Check if this part refers to a list
        if part.endswith('[]'):
            # Remove the [] notation
            key = part[:-2]
            
            # Navigate to the list
            if isinstance(current, dict) and key in current:
                list_value = current[key]
                if isinstance(list_value, list):
                    # Continue with all list items
                    remaining_path = '.'.join(path_parts[path_parts.index(part) + 1:])
                    if remaining_path:
                        # There are more path components, recurse for each list item
                        for item in list_value:
                            result = _get_json_item(item, remaining_path)
                            if result is not None:
                                values.append(str(result))
                    else:
                        # No more path, just collect the list items
                        for item in list_value:
                            values.append(str(item))
                    # Return concatenated values and stop processing
                    return ' '.join(values) if values else None
            else:
                return None
        else:
            # Regular dict key navigation
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
    
    # Return the final value
    return current if current is not None else None


def run(ctx, project, list_keys=False):
    logger = setup_logging(command="extract_meta", project=project, debug=ctx.obj["debug"])

    log_command_start(logger, "Extracting metadata", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
        
    # Get JSON files from converted directory
    json_files = get_sample_files(project, logger, kind="json", ctx=ctx)
    if not json_files:
        return
        
    logger.info(f"Processing {len(json_files)} .json file(s)")
        
    if list_keys:
        # If the --list argument is provided, extract metadata keys from each JSON file and store them in a text file
        # This will be the basis for the user to create metadata_config.yaml

        keys = set()
        for idx,json_file in enumerate(json_files):
            try:
                # Load the instrument section of the json file
                instrument_data = get_json_section(json_file, 'instrument', logger)

                # If it is found, extract all the metadata keys it contains
                if instrument_data is not None:
                    new_keys = set(_get_json_structure(instrument_data))
                    n_new = len(new_keys - keys)
                    if n_new > 0:
                        keys.update(new_keys)
                    logger.info(f"Found {n_new} " + ("new " if idx>0 else "") + f"metadata keys in '{json_file.name}'")
                
            except ijson.JSONError as e:
                raiseCytoError(f"Failed to parse .json file '{json_file.name}': {e}", logger)
            except Exception as e:
                raiseCytoError(f"Error reading '{json_file.name}': {e}", logger)

        # If there are multiple json files, deduplicate keys
        if len(json_files) > 1:
            logger.info(f"Found {len(keys)} unique metadata items across all .json files")

        # Make sure config directory exists
        meta_dir = ensure_project_dir(project, "meta")

        # Write keys to file
        keys_file = meta_dir / "available_metadata_fields.txt"
        with open(keys_file, 'w') as f:
            for key_path in sorted(keys):
                f.write(f"{key_path}\n")
        
        logger.info(f"Available metadata fields written to {keys_file}. Use them in the sample, acq, and process sections of the config.yaml file to define metadata extraction.")

    else:
        # Otherwise, in normal operations, extract specific metadata items based on config.yaml

        config_file = Path(project) / "config" / "config.yaml"
        
        if not config_file.exists():
            raiseCytoError(f"Configuration file not found: '{config_file}', run 'cytoprocess create {project}' again.", logger)
        
        logger.info(f"Read metadata fields list from '{config_file}'")
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Prepare data structure: list of dicts, one per JSON file
        metadata_rows = []
        
        for json_file in json_files:
            try:
                logger.debug(f"Extracting metadata from '{json_file.name}'")

                # Load the instrument section of the json file
                instrument_data = get_json_section(json_file, 'instrument', logger)

                # If it is found, extract all the metadata keys it contains
                if instrument_data is None:
                    continue

                # Create a row for this file
                row = {}
                
                # Define the sample_id to join this with the rest of the data
                row['sample_id'] = json_file.stem
                # Process each section (sample, acq, process)
                for section_name in ['sample', 'acq', 'process']:
                    section_keys = config.get(section_name)
                    if not isinstance(section_keys, dict):
                        continue
                    
                    logger.debug(f"Processing section: {section_name}")

                    # Extract each key in this section
                    for json_path, column_name in section_keys.items():
                        # Prepend section name to column name
                        full_column_name = f"{section_name}_{column_name}"
                        
                        # Get the value from the JSON
                        value = _get_json_item(instrument_data, json_path)
                        
                        if value is None:
                            logger.debug(f"Key '{json_path}' not found in {json_file.name}")
                        else:
                            row[full_column_name] = value

                    # Force the inclusion of pixel size because we need it later
                    # (to draw the scale bar on images)
                    row["__pixel_size__"] = _get_json_item(instrument_data, 'measurementSettings.CytoSettings.CytoSettings.iif.ImageScaleMuPerPixelP')
                
                metadata_rows.append(row)
                logger.info(f"Extracted {len(row)-2} metadata fields from '{json_file.name}'")
                # NB: -2 to exclude the sample_id and __pixel_size__ fields
                
            except ijson.JSONError as e:
                raiseCytoError(f"Failed to parse .json file '{json_file.name}': {e}", logger)
            except Exception as e:
                raiseCytoError(f"Error processing '{json_file.name}': {e}", logger)
        
        # Save to paquet in work directory
        work_dir = ensure_project_dir(project, "work")
        output_file = work_dir / "sample_metadata_from_instrument.parquet"
        logger.info(f"Saving metadata to '{output_file}'")
        
        # Create DataFrame from newly extracted metadata
        new_df = pd.DataFrame(metadata_rows)

        # Check if the parquet file already exists
        if output_file.exists():
            # TODO consider requiring --force here like in other commands
            logger.debug(f"Metadata file exists, updating rows")
            existing_df = pd.read_parquet(output_file)
            
            # Remove rows from existing_df that have the same sample_id as in new_df
            existing_df = existing_df[~existing_df['sample_id'].isin(new_df['sample_id'])]

            logger.debug(f"Updating/appending {len(new_df)} row(s)")
            df = pd.concat([existing_df, new_df], ignore_index=True)

        else:
            logger.debug(f"Creating new metadata file")
            df = new_df
        
        # Sort by sample_id, for consistency
        df = df.sort_values('sample_id').reset_index(drop=True)

        df.to_parquet(output_file, index=False)
        logger.debug(f"Metadata shape: {df.shape[0]} rows × {df.shape[1]} columns")

    log_command_success(logger, "Extract metadata")

