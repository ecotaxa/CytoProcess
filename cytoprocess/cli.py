#
# Command line interface for CytoProcess
#
# This consists of a main command (cytoprocess) with subcommands for each processing step.
#

import click
from pathlib import Path
from cytoprocess.utils import setup_logging

# List commands in the order they appear in this file
class NaturalOrderGroup(click.Group):
    def list_commands(self, ctx):
        return self.commands.keys()


@click.group(cls=NaturalOrderGroup)
@click.option("--debug", is_flag=True, default=False, help="Show debugging messages.")
@click.option("--sample", default=None, help="Limit processing to a single sample, specified by the (quoted) name of the .cyz file.")
@click.pass_context
def cli(ctx, debug, sample):
    """CytoProcess command line interface."""
    # Prepare the context object which contains global options
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    # Normalize sample name if provided
    # (remove path and .cyz extension if present)
    if sample:
        sample_path = Path(sample)
        sample = sample_path.stem
    ctx.obj["sample"] = sample
    # TODO add a global mask option to process all samples that match the mask (e.g. "sample1_*" to process all samples that start with "sample1_")


@cli.command(name="install")
@click.option("--force", is_flag=True, default=False, help="Force (re)installation of the latest release even if Cyz2Json already exists")
@click.pass_context
def install(ctx, force):
    """Install depency: Cyz2Json converter."""
    from cytoprocess.commands import install
    install.run(ctx, force=force)


@cli.command(name="create")
@click.argument("project")
@click.pass_context
def create(ctx, project):
    """Create a new CytoProcess project directory."""
    from cytoprocess.commands import create
    create.run(ctx, project=project)


@cli.command(name="list")
@click.argument("project", type=click.Path(exists=True))
@click.option("--extra-fields", default="object_lon,object_lat,object_date,object_time,object_depth_min,object_depth_max,object_lon_end,object_lat_end", help="Comma-separated list of extra fields to add as columns in samples.csv")
@click.pass_context
def list_samples(ctx, project, extra_fields):
    """List samples and create/update samples.csv."""
    from cytoprocess.commands import list as list_cmd
    list_cmd.run(ctx, project=project, extra_fields=extra_fields)


@cli.command(name="convert")
@click.argument("project")
@click.option("--force", is_flag=True, default=False, help="Force conversion even if .json files already exist")
@click.pass_context
def convert(ctx, project, force):
    """Convert .cyz files to .json format."""
    from cytoprocess.commands import convert
    convert.run(ctx, project=project, force=force)


@cli.command(name="extract_meta")
@click.argument("project")
@click.option("--list", "list_keys", is_flag=True, default=False, help="List all metadata items found in the .json file(s) instead of extracting some of them")
@click.option("--force", is_flag=True, default=False, help="Force extraction even if output files already exist")
@click.pass_context
def extract_meta(ctx, project, list_keys, force):
    """Extract sample metadata from .json files."""
    from cytoprocess.commands import extract_meta
    extract_meta.run(ctx, project=project, list_keys=list_keys, force=force)


@cli.command(name="extract_cyto")
@click.argument("project")
@click.option("--list", "list_keys", is_flag=True, default=False, help="List all cytometric fields paths found in the .json file(s) instead of extracting some of them")
@click.option("--force", is_flag=True, default=False, help="Force extraction even if output files already exist")
@click.pass_context
def extract_cyto(ctx, project, list_keys, force):
    """Extract cytometric features from .json files."""
    from cytoprocess.commands import extract_cyto
    extract_cyto.run(ctx, project=project, list_keys=list_keys, force=force)


@cli.command(name="summarise_pulses")
@click.argument("project")
@click.option("--n-poly", default=10, help="Number of polynomial coefficients")
@click.option("--force", is_flag=True, default=False, help="Force processing even if output files already exist")
@click.option("--max-cores", type=int, default=15, help="Maximum number of CPU cores to use for parallel processing")
@click.pass_context
def summarise_pulses(ctx, project, n_poly, force, max_cores):
    """Summarise pulse shapes."""
    from cytoprocess.commands import summarise_pulses
    summarise_pulses.run(ctx, project=project, n_poly=n_poly, force=force, max_cores=max_cores)


@cli.command(name="extract_images")
@click.argument("project", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Force extraction even if output files already exist")
@click.pass_context
def extract_images(ctx, project, force):
    """Extract images from .json files."""
    from cytoprocess.commands import extract_images
    extract_images.run(ctx, project, force=force)


@cli.command(name="compute_features")
@click.argument("project")
@click.option("--force", is_flag=True, default=False, help="Force processing even if output files already exist")
@click.option("--max-cores", type=int, default=15, help="Maximum number of CPU cores to use for parallel processing")
@click.pass_context
def compute_features(ctx, project, force, max_cores):
    """Compute features from extracted images."""
    from cytoprocess.commands import compute_features
    compute_features.run(ctx, project=project, force=force, max_cores=max_cores)


@cli.command(name="prepare")
@click.argument("project", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Force preparation even if output files already exist")
@click.option("--only-tsv", is_flag=True, help="Only create TSV files, skip zip file creation (useful to update metadata only)")
@click.option("--max-cores", type=int, default=15, help="Maximum number of CPU cores to use for parallel processing")
@click.pass_context
def prepare(ctx, project, force, only_tsv, max_cores):
    """Prepare .tsv and images for EcoTaxa."""
    from cytoprocess.commands import prepare
    prepare.run(ctx, project, force=force, only_tsv=only_tsv, max_cores=max_cores)


@cli.command(name="upload")
@click.argument("project", type=click.Path(exists=True))
@click.option("--username", "-u", help="EcoTaxa email address")
@click.option("--password", "-p", help="EcoTaxa password")
@click.pass_context
def upload(ctx, project, username, password):
    """Upload files to EcoTaxa. """
    from cytoprocess.commands import upload
    upload.run(ctx, project, username=username, password=password)


@cli.command(name="all")
@click.argument("project")
@click.option("--force", is_flag=True, default=False, help="Force processing even if output already exists")
@click.option("--n-poly", default=10, help="Number of polynomial coefficients")
@click.option("--max-cores", type=int, default=15, help="Maximum number of CPU cores to use for parallel processing")
@click.pass_context
def all(ctx, project, force, n_poly, max_cores):
    """Run all processing steps in sequence."""
    from cytoprocess.commands import (
        convert,
        extract_meta,
        extract_cyto,
        summarise_pulses,
        extract_images,
        compute_features,
        prepare,
        upload,
    )
    
    logger = setup_logging(command="all", project=project, debug=ctx.obj["debug"])
    logger.info(f"Running all processing steps for project: {project}")
    
    convert.run(ctx, project=project, force=force)
    
    extract_meta.run(ctx, project=project, list_keys=False)

    extract_cyto.run(ctx, project=project, list_keys=False, force=force)
    
    summarise_pulses.run(ctx, project=project, force=force, n_poly=n_poly, max_cores=max_cores)

    extract_images.run(ctx, project=project, force=force)
    
    compute_features.run(ctx, project=project, force=force, max_cores=max_cores)
    
    prepare.run(ctx, project=project, force=force, max_cores=max_cores)
    
    upload.run(ctx, project=project)
    
    logger.info("All processing steps completed successfully")


@cli.command(name="clean")
@click.argument("project")
@click.pass_context
def clean(ctx, project):
    """Remove intermediate files in the project."""
    from cytoprocess.commands import clean
    clean.run(ctx, project=project)


def main(argv=None):
    cli(prog_name="cytoprocess", args=argv)


if __name__ == "__main__":
    main()
