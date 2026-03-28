# CytoProcess

Package to process images and their features from .cyz files from the CytoSense and upload them to EcoTaxa.


## Installation

NB: As for all things Python, you should preferrably install CytoProcess within a Python venv/coda environment. The package is tested with Python=3.11 and should therefore work with this or a more recent version. To create a conda environment, use

```bash
conda create -n cytoprocess python=3.11
conda activate cytoprocess
```

Then install the sable version with

```bash
pip install cytoprocess
```

*or* the development version with

```bash
pip install git+https://github.com/jiho/cytoprocess.git
```

The Python package includes a command line tool, which should become available from within a terminal. To try it and output the help message

```bash
cytoprocess
```

CytoProcess depends on [Cyz2Json](https://github.com/OBAMANEXT/cyz2json). To install it, run

```bash
cytoprocess install
```


## Usage

CytoProcess uses the concept of "project". A project corresponds conceptually to a cruise, a time series, etc. Practically, it is a directory with a specific set of subdirectories that contain all files related to the cruise/time series/etc. It corresponds to a single EcoTaxa project.

Each .cyz file is considered as a "sample" (and will correspond to an EcoTaxa sample).

```
my_project/
    config      configuration files
    raw         source .cyz files
    converted   .json files converted from .cyz by Cyz2Json
    meta        files storing metadata and is mapping from .json to EcoTaxa
    images      images extracted from the .json files, in one subdirectory per file
    work        information extracted by the various processing steps (metadata, pulses, features, etc.)
    ecotaxa     .zip files ready for upload in EcoTaxa
    logs        logs of all commands executed on this project, per day
```

A CytoProcess command line looks like

```bash
cytoprocess --global-option command --command-option project_directory
```

To know which global options and which commands are available, use

```bash
cytoprocess --help
```

To know which options are available for a given command

```bash
cytoprocess command --help
```

### Creating and populating a project

Use

```bash
cytoprocess create path/to/my_project
```

Then copy/move the .cyz files that are relevant for this project in `my_project/raw`. If you have an archive of .cyz files organised differently, you should be able to symlink them in `my_project/raw` instead of copying them.


### Processing samples in a project

List available samples and create the `meta/samples.csv` file

```bash
cytoprocess list path/to/my_project
```

Manually enter the required metadata (such as lon, lat, etc.) in the .csv file. You can add or remove columns as you see fit, you can use the option `--extra-fields` to determine which to add. The conventions follow those of EcoTaxa. Then performs all processing steps, for all samples, with default options 

```bash
cytoprocess all path/to/my_project
```

If you want to know the details, or proceed manually, the steps behind `all` are:

```bash
# convert .cyz files into .json and create a placeholder its metadata
cytoprocess convert path/to/project

# extract sample/acq/process level metadata from each .json file
cytoprocess extract_meta path/to/project
# extract cytometric features for each imaged particle
cytoprocess extract_cyto path/to/project
# compute pulse shapes polynomial summaries for each imaged particle
cytoprocess summarise_pulses path/to/project

# extract images and their features
cytoprocess extract_images path/to/project

# prepare files for ecotaxa upload
cytoprocess prepare path/to/project
# upload them to EcoTaxa
cytoprocess upload path/to/project
```


### Customisation

To process a single sample, use

```bash
cytoprocess --sample 'name_of_cyz_file' command path/to/project
```

All commands will skip the processing of a given sample if the output is already present. To re-process and overwrite, use the `--force` option.

For metadata and cytometric features extraction (`extract_meta` and `extract_cyto`), information from the json file needs to be curated and translated into EcoTaxa metadata columns. This is defined in the configuration file, by `key: value` pairs of the form `json.fields.item.name: ecotaxa_name`. To get the list of possible json fields, use the `--list` option for `extract_meta` or `extract_cyto`; it will write a text file in `meta` with all possibilities. You can then copy-paste them to `config/config.yaml`.

Even with all these fields available, the CytoSense may not record relevant metadata such as latitude, longitude, and date of each sample, which EcoTaxa needs to filter the data or export it to other data bases. You can provide such fields manually by editing the `meta/samples.csv` file.


### Cleaning up after processing

Because everything is stored in the EcoTaxa files and can be re-generated from the .cyz files, you may want to remove the intermediate files, to reclaim disk space. This is done with

```bash
cytoprocess clean path/to/project
```

## Development

Fork this repository, clone your fork.

Prepare your development environment by installing the dependencies within a conda environment

```bash
conda create -n cytoprocess python=3.11
conda activate cytoprocess
pip install -e .
```

This creates a `cytoprocess.egg-info` directory at the root of the package's directory. It is safely ignored by git (and you should too).

Now, either run commands as you normally would

```bash
cytoprocess --help
```

or call the module explicitly

```bash
python -m cytoprocess --help
```

Any edits made to the files are immediately reflected in the output (because the package was installed in "editable" mode: `pip install -e ...` ; or is run directly as a module: `python -m ...`).
