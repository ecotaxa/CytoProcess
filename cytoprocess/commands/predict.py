import importlib
import importlib.util
from pathlib import Path

import click
import pandas as pd

from cytoprocess.logging import setup_logging, log_command_start, log_command_success
from cytoprocess.project import list_sample_assets, path_to_sample_asset
from cytoprocess.utils import raiseCytoError


def _load_predict_fn(spec: str):
    """
    Load a predict function from a file path or dotted module spec.

    Args:
        spec: A string specifying the function to load, in one of the following formats:
        - "path/to/model.py::func_name": loads func_name from the given .py file
        - "my_module.func_name": imports my_module and returns func_name from it
    
    Returns:
        The loaded function object.
    """
    if "::" in spec:
        file_path, func_name = spec.rsplit("::", 1)
        mod_spec = importlib.util.spec_from_file_location("_cytoprocess_user_predict", file_path)
        if mod_spec is None or mod_spec.loader is None:
            raise ValueError(f"Cannot load file: '{file_path}'")
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
    else:
        module_path, func_name = spec.rsplit(".", 1)
        module = importlib.import_module(module_path)

    if not hasattr(module, func_name):
        raise AttributeError(f"Function '{func_name}' not found in '{spec}'")
    return getattr(module, func_name)


def run(ctx: click.Context, project: Path, function_spec: str, force: bool = False):
    # Housekeeping for the command
    logger = setup_logging(command="predict", project=project, debug=ctx.obj["debug"])
    log_command_start(logger, "Running predictions", project)
    logger.debug("Context: %s", getattr(ctx, "obj", {}))
    if force:
        logger.debug("Force flag enabled, existing prediction files will be overwritten")

    logger.debug(f"Loading predict function from '{function_spec}'")
    try:
        predict_fn = _load_predict_fn(function_spec)
    except (ValueError, AttributeError, ImportError, FileNotFoundError) as e:
        raiseCytoError(f"Failed to load predict function from '{function_spec}': {e}", logger)
        return

    # List samples in work, filtered by --sample if provided
    samples_mask = ctx.obj["sample"]
    sample_dirs = list_sample_assets(project, "dir", logger, samples_mask=samples_mask)
    if not sample_dirs:
        return
    sample_ids = [d.name for d in sample_dirs]

    logger.info(f"Running predictions for {len(sample_ids)} sample(s)")

    for sample_id in sample_ids:
        logger.info(f"'{sample_id}'")

        predictions_file = project / path_to_sample_asset(sample_id, "predictions", logger)
        if predictions_file.exists() and not force:
            logger.info(f"  Skipping, predictions file already exists (use --force to overwrite)")
            continue

        # Get cytometric features
        cytometric_features_file = project / path_to_sample_asset(sample_id, "cytometric_features", logger)
        if not cytometric_features_file.exists():
            logger.warning(f"Missing cytometric features, run `cytoprocess --sample '{sample_id}' extract_cyto {project}`")
            continue
        cytometric_df = pd.read_parquet(cytometric_features_file)
        if cytometric_df.empty:
            logger.warning(f"No particles in sample '{sample_id}', skipping.")
            continue

        # Get image features
        image_features_file = project / path_to_sample_asset(sample_id, "image_features", logger)
        if not image_features_file.exists():
            logger.warning(f"Missing image features, run `cytoprocess --sample '{sample_id}' extract_images {project}`")
            continue
        image_features_df = pd.read_parquet(image_features_file)

        # Combine features and prepare image paths
        features_df = cytometric_df.merge(image_features_df, on=["sample_id", "object_id"], how="left")

        images_dir = project / path_to_sample_asset(sample_id, "images", logger)
        image_paths = [str(images_dir / f"{obj_id.replace(sample_id + '_', '', 1)}_img.jpg") for obj_id in features_df["object_id"]]
        drop_cols = ["sample_id", "object_id"] + [c for c in features_df.columns if c.startswith("acq_")]
        features_data = features_df.drop(columns=drop_cols)

        # Call the prediction function
        logger.debug(f"  Calling predict function on {len(image_paths)} objects")
        try:
            predictions = predict_fn(image_paths, features_data)
        except Exception as e:
            raiseCytoError(f"  The prediction function raised an error for sample '{sample_id}': {e}", logger)
            continue

        # Handle the output
        if isinstance(predictions, dict):
            predictions = pd.DataFrame(predictions)
        if not isinstance(predictions, pd.DataFrame):
            raiseCytoError(f"  The prediction function must return a dict or a pandas DataFrame, got {type(predictions)}", logger)
            continue

        if len(predictions) != len(features_data):
            raiseCytoError(
                f"  The prediction function returned {len(predictions)} rows but expected {len(features_data)}",
                logger
            )
            continue

        if "annotation_category" not in predictions.columns:
            raiseCytoError(
                f"  The prediction function must return a dict/DataFrame containing an 'annotation_category' element/column",
                logger
            )
            continue

        if "annotation_status" not in predictions.columns:
            predictions["annotation_status"] = "predicted"

        predictions.columns = [f"object_{c}" for c in predictions.columns]
        predictions.insert(0, "object_id", features_df["object_id"].values)
        predictions.insert(0, "sample_id", sample_id)
        predictions.to_parquet(predictions_file)

        logger.info(f"  Saved {len(predictions)} predictions ({len(predictions.columns) - 2} column(s)) to '{predictions_file}'")

    log_command_success(logger, "Predictions")
