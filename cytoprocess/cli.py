#
# Command line interface for CytoProcess
#
# This consists of a main command (cytoprocess) with subcommands for each processing step.
#

from pathlib import Path

import click

from cytoprocess.logging import setup_logging

# List commands in the order they appear in this file
class NaturalOrderGroup(click.Group):
    def list_commands(self, ctx):
        return self.commands.keys()


@click.group(cls=NaturalOrderGroup)
@click.option("--debug", "-d", is_flag=True, default=False, help="Show debugging messages.")
@click.option("--sample", "-s", default=None, help="Limit processing to the sample(s) matching the given string, including globing patterns (e.g. 'sample_123' to process only the sample called exactly that or '*2025* to process all samples with '2025' in their name).")
@click.pass_context
def cli(ctx, debug, sample):
    """
    CytoProcess command line interface
    
    CytoProcess is a tool to process CytoSense images and upload them to EcoTaxa. It uses the concept of "project" to organise the data and metadata. It provides commands to create a project, convert raw files, extract metadata and features, summarise pulse shapes, extract images, optionally predict their classification, prepare files for EcoTaxa, and upload them.
    """
    # Prepare the context object which contains global options
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    # Normalize sample name if provided
    # (remove path and .cyz extension if present)
    if sample:
        sample_path = Path(sample)
        sample = sample_path.stem
    ctx.obj["sample"] = sample


@cli.command(name="install")
@click.option("--force", "-f", is_flag=True, default=False, help="Force (re)installation of the latest release even if Cyz2Json already exists.")
@click.pass_context
def install(ctx, force):
    """
    Install dependency: Cyz2Json converter.
    
    This tool is required to convert .cyz files in a readable .json format. It is distributed from https://github.com/OBAMANEXT/cyz2json. This command installs the latest release automatically.
    """
    from cytoprocess.commands import install
    install.run(ctx, force=force)


@cli.command(name="create")
@click.argument("project")
@click.pass_context
def create(ctx, project):
    """Create a new CytoProcess project directory."""
    from cytoprocess.commands import create
    create.run(ctx, project=Path(project).expanduser())


@cli.command(name="list")
@click.argument("project", type=click.Path(exists=True))
@click.option("--extra-fields", "-e", default="object_lon,object_lat,object_date,object_time,object_depth_min,object_depth_max,object_lon_end,object_lat_end", help="Comma-separated list of extra fields to add as columns in samples.csv.")
@click.pass_context
def list_samples(ctx, project, extra_fields):
    """
    List samples and create/update meta/samples.csv.
    
    Run this after creating the project and after adding new .cyz files to it. Once run, the file meta/samples.csv should be edited to add metadata for each sample. The default metadata fields are very relevant for EcoTaxa (location, time, etc.).
    """
    from cytoprocess.commands import list as list_cmd
    list_cmd.run(ctx, project=Path(project).expanduser(), extra_fields=extra_fields)


@cli.command(name="convert")
@click.argument("project", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, default=False, help="Force conversion even if .json files already exist.")
@click.pass_context
def convert(ctx, project, force):
    """Convert .cyz files to .json format."""
    from cytoprocess.commands import convert
    convert.run(ctx, project=Path(project).expanduser(), force=force)


@cli.command(name="extract_meta")
@click.argument("project", type=click.Path(exists=True))
@click.option("--list", "-l", "list_keys", is_flag=True, default=False, help="List all metadata items found in the .json file(s) instead of extracting some of them.")
@click.option("--force", "-f", is_flag=True, default=False, help="Force extraction even if output files already exist.")
@click.pass_context
def extract_meta(ctx, project, list_keys, force):
    """
    Extract instrument metadata from .json files.
    
    These are metadata fields stored in the .json by the CytoSense itself. They are useful to describe the acquisition of the samples.

    The names of the fields can by found by using the `--list` option, and should then be mapped to EcoTaxa metadata columns in config.xml.
    """
    from cytoprocess.commands import extract_meta
    extract_meta.run(ctx, project=Path(project).expanduser(), list_keys=list_keys, force=force)


@cli.command(name="extract_cyto")
@click.argument("project", type=click.Path(exists=True))
@click.option("--list", "-l", "list_keys", is_flag=True, default=False, help="List all cytometric fields paths found in the .json file(s) instead of extracting some of them.")
@click.option("--force", "-f", is_flag=True, default=False, help="Force extraction even if output files already exist.")
@click.pass_context
def extract_cyto(ctx, project, list_keys, force):
    """
    Extract cytometric features from .json files.
    
    These correspond to what is traditionally called the "listmode" files: they are summaries of the pulse shape per channel for each object (maximum value, average value, etc.). Some can be directly informative biologically and all can be used by machine learning algorithms to predict classifications.
    
    Similarly, to the metadata fields, the names of the cytometric features can be found by using the `--list` option, and should then be mapped to EcoTaxa feature columns in config.xml.
    """
    from cytoprocess.commands import extract_cyto
    extract_cyto.run(ctx, project=Path(project).expanduser(), list_keys=list_keys, force=force)


@cli.command(name="summarise_pulses")
@click.argument("project", type=click.Path(exists=True))
@click.option("--n-poly", "-n",default=10, help="Number of polynomial coefficients")
@click.option("--force", "-f", is_flag=True, default=False, help="Force processing even if output files already exist.")
@click.option("--max-cores", "-m", type=int, default=15, help="Maximum number of CPU cores to use for parallel processing.")
@click.pass_context
def summarise_pulses(ctx, project, n_poly, force, max_cores):
    """
    Summarise pulse shapes.
    
    The pulse shapes for each particle are standardised between 0 and 1 and then approximated by a polynomial of degree `n_poly` (default 10). The coefficients of the polynomial are then used as features in EcoTaxa. This is a way to summarise the pulse shapes while keeping their general form, which can be informative for classification.
    
    In addition, a plot of the standardised pulse shape is created. This plot is uploaded to EcoTaxa as the third image of each object.
    """
    from cytoprocess.commands import summarise_pulses
    summarise_pulses.run(ctx, project=Path(project).expanduser(), n_poly=n_poly, force=force, max_cores=max_cores)


@cli.command(name="extract_images")
@click.argument("project", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, default=False, help="Force extraction even if output files already exist.")
@click.option("--max-cores", "-m", type=int, default=15, help="Maximum number of CPU cores to use for parallel processing.")
@click.pass_context
def extract_images(ctx, project, force, max_cores):
    """
    Extract images from .json files.
    
    Extract the images from the .json files and segments the main object in each. It stores a file for the image and for the mask, which are both uploaded to EcoTaxa.

    Some usual features are measured on the segmented object (area, perimeter, etc.), which are added to the features extracted from the pulse shapes and can be used for classification or biological interpretation.
    """
    from cytoprocess.commands import extract_images
    extract_images.run(ctx, project=Path(project).expanduser(), force=force, max_cores=max_cores)


@cli.command(name="prepare")
@click.argument("project", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, default=False, help="Force preparation even if output files already exist.")
@click.pass_context
def prepare(ctx, project, force):
    """
    Prepare .tsv and images for EcoTaxa.
    
    Create a .zip archive in the `ecotaxa` folder with: (1) the .tsv file with the metadata and features for each object and (2) three images per object (image, mask, pulse plot), for each sample.
    """
    from cytoprocess.commands import prepare
    prepare.run(ctx, project=Path(project).expanduser(), force=force)


@cli.command(name="upload")
@click.argument("project", type=click.Path(exists=True))
@click.option("--username", "-u", help="EcoTaxa email address.")
@click.option("--password", "-p", help="EcoTaxa password.")
@click.option("--update", is_flag=True, default=False, help="Only update the metadata for existing samples.")
@click.pass_context
def upload(ctx, project, username, password, update):
    """
    Upload files to EcoTaxa.
    
    The .zip files prepared are uploaded and then imported into an EcoTaxa project, configured in config.xml.
    
    If the `--update` flag is used, only the metadata of existing samples is updated, without re-uploading the images. This is useful to update the metadata after editing samples.csv: it only requires to re-run the `prepare` step and then `upload --update`.
    """
    from cytoprocess.commands import upload
    upload.run(ctx, project=Path(project).expanduser(), username=username, password=password, update=update)


@cli.command(name="all")
@click.argument("project", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, default=False, help="Force processing even if output already exists.")
@click.option("--n-poly", "-n", default=10, help="Number of polynomial coefficients.")
@click.option("--max-cores", "-m", type=int, default=15, help="Maximum number of CPU cores to use for parallel processing.")
@click.pass_context
def all(ctx, project, force, n_poly, max_cores):
    """Run all steps from convert to upload in sequence."""
    from cytoprocess.commands import (
        convert,
        extract_meta,
        extract_cyto,
        summarise_pulses,
        extract_images,
        prepare,
        upload,
    )
    
    logger = setup_logging(command="all", project=Path(project).expanduser(), debug=ctx.obj["debug"])
    logger.info(f"Running all processing steps for project: {project}")
    
    convert.run(ctx, project=Path(project).expanduser(), force=force)
    
    extract_meta.run(ctx, project=Path(project).expanduser(), list_keys=False)

    extract_cyto.run(ctx, project=Path(project).expanduser(), list_keys=False, force=force)
    
    summarise_pulses.run(ctx, project=Path(project).expanduser(), force=force, n_poly=n_poly, max_cores=max_cores)

    extract_images.run(ctx, project=Path(project).expanduser(), force=force, max_cores=max_cores)
        
    prepare.run(ctx, project=Path(project).expanduser(), force=force)
    
    upload.run(ctx, project=Path(project).expanduser())
    
    logger.info("All processing steps completed successfully")


@cli.command(name="status")
@click.argument("project", type=click.Path(exists=True))
@click.option("--width", "-w", default=40, type=int, help="Width of the sample ID display (truncated with ellipsis if too long).")
@click.pass_context
def status(ctx, project, width):
    """Show per-sample processing status."""
    from cytoprocess.commands import status
    status.run(ctx, project=Path(project).expanduser(), width=width)


@cli.command(name="clean")
@click.argument("project", type=click.Path(exists=True))
@click.option("--older-than", "-o", default=None, type=int, help="Remove log files older than this many days (by default, do not remove anything).")
@click.pass_context
def clean(ctx, project, older_than):
    """
    Remove intermediate files in the project.
    
    Remove the `work` directory: everything in it can be re-generated by re-running the commands and the relevant content is stored in the .zip files in `ecotaxa`.

    Optionnally, log files older than a certain number of days can also be removed.
    """
    from cytoprocess.commands import clean
    clean.run(ctx, project=Path(project).expanduser(), older_than=older_than)


@cli.command(name="predict")
@click.argument("project", type=click.Path(exists=True))
@click.option("--model", "-m", required=True, help="A function encapsulating the prediction model, specificed as 'path/to/model.py::func_name' or 'my_module.func_name'.")
@click.option("--force", "-f", is_flag=True, default=False, help="Force re-prediction even if output already exists. ")
@click.pass_context
def predict(ctx, project, model, force):
    """
    Run a user-provided model to predict classifications.

    \b
    The function should accept two arguments:
    1. paths: a list of absolute paths to the images,
    2. features: a DataFrame with one row per image and cytometric + image
                 features as columns (the cytometric features retained are
                 defined in config.xml).

    It should return a DataFrame (or a dictionary that can be converted to one) with rows matching the input images (same number, same order) and at least one column called 'annotation_category' containing the predicted EcoTaxa category name for each image. Other columns can be added. All column names will be prepended with 'object_' before their import into EcoTaxa.
    
    NB: Images contain a 31 pixels-high scale bar at the bottom. It should be cropped out before feeding the image to a deep learning model.
    """
    from cytoprocess.commands import predict
    predict.run(ctx, project=Path(project).expanduser(), function_spec=model, force=force)



def main(argv=None):
    cli(prog_name="cytoprocess", args=argv)


if __name__ == "__main__":
    main()
