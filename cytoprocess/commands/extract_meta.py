import click
import ijson
import pandas as pd
from pathlib import Path
from cytoprocess.utils import (
    list_sample_assets, path_to_sample_asset,
    get_json_section, load_config,
    setup_logging, log_command_start, log_command_success,
    raiseCytoError
)

def _get_json_structure(json_data: dict, prefix=""):
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


def _get_json_item(json_data: dict, path: str):
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


def run(ctx: click.Context, project: Path, list_keys: bool=False, force: bool=False):
    # Housekeeping for the command
    logger = setup_logging(command="extract_meta", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Extracting metadata", project)
    if force:
        logger.debug("Force flag enabled: existing metadata files will be overwritten")
    logger.debug("Context: %s", getattr(ctx, "obj", {}))


    # Get JSON files from converted directory
    json_files = list_sample_assets(project, kind="json", logger=logger, ctx=ctx)
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

        # Write keys to file
        keys_file = project / "config" / "available_metadata_fields.txt"
        with open(keys_file, 'w') as f:
            for key_path in sorted(keys):
                f.write(f"{key_path}\n")
        
        logger.info(f"Available metadata fields written to {keys_file}. Use them in the sample, acq, and process sections of the config.yaml file to define metadata extraction.")

    else:
        # Otherwise, in normal operations, extract specific metadata items based on config.yaml
        config = load_config(project, logger)

        # Ensure work directory exists to store the output
        work_dir = project / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
                
        for json_file in json_files:
            # Get sample_id from file name
            sample_id = json_file.parents[0].name
            output_file = project / path_to_sample_asset(sample_id, 'metadata', logger)

            logger.info(f"'{sample_id}'")
           
            # Skip if output file exists and force is not set
            if output_file.exists() and not force:
                logger.info(f"  Skipping, output file already exists (use --force to overwrite)")
                continue

            try:
                logger.debug(f"Extracting metadata for '{sample_id}'")

                # Load the instrument section of the json file
                instrument_data = get_json_section(json_file, 'instrument', logger)

                if instrument_data is None:
                    logger.warning(f"No 'instrument' section found in '{json_file.name}', skipping metadata extraction for this file")
                    continue

                # Initialise metadata dictionary with sample_id
                meta = {'sample_id': sample_id}
                
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
                            meta[full_column_name] = value
                
                logger.info(f"  Extracted {len(meta)-1} metadata fields")
                # NB: -1 to exclude the sample_id field
                
            except ijson.JSONError as e:
                raiseCytoError(f"Failed to parse .json file '{json_file.name}': {e}", logger)
            except Exception as e:
                raiseCytoError(f"Error processing '{json_file.name}': {e}", logger)
        
            logger.info(f"  Saving to '{output_file}'")
            pd.DataFrame([meta]).to_parquet(output_file, index=False)

    log_command_success(logger, "Extract metadata")
