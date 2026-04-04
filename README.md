<img src="CytoProcess_logo.svg" alt="CytoProcess logo" width="300"/>

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


## Quick start

CytoProcess uses the concept of "project". A project corresponds conceptually to a cruise, a time series, etc. Practically, it is a directory with a specific set of subdirectories that contain all files related to the cruise/time series/etc. It corresponds to a single EcoTaxa project.

Each .cyz file is considered as a "sample" (and will correspond to an EcoTaxa sample).

A project is organised like so

```
my_project/
    config      configuration files
    raw         source .cyz files
    meta        file storing manually-provided metadata for each sample(lat, lon, etc.)
    work        data extracted by the various processing steps
        <sample_id_1>                in one folder per sample
            converted_data.json          file converted from .cyz by Cyz2Json
            cytometric_features.parquet  average cytometric measurement per image
            image_features.parquet       features computed on each image (area, etc.)
            images                       images with scale bar and mask for the particle
            metadata.parquet             instrument metadata extracted from the .json file
            pulses_plots                 plot of the pulse shapes of imaged particles
            pulses_summaries.parquet     polynomial summaries of the pulse shapes
        <sample_id_2>
            ...
    ecotaxa     .zip files ready for upload in EcoTaxa
    logs        logs of all commands executed on this project, split per day
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

List available raw samples and create the `meta/samples.csv` file with

```bash
cytoprocess list path/to/my_project
```

Manually enter the required metadata (such as lon, lat, etc.) in the .csv file. You can add or remove columns as you see fit, you can use the option `--extra-fields` (or `-e`) to change the default columns added. The conventions follow those of EcoTaxa.

Then, perform all processing steps, for all samples, with default options 

```bash
cytoprocess all path/to/my_project
```

To check how far along the processing of each sample is, use

```bash
cytoprocess status path/to/project
```

### Detailed usage


If you want to know the details, or proceed manually, the steps behind `all` are:

```bash
# convert .cyz files into .json and create a placeholder its metadata
cytoprocess convert path/to/project

# extract instrument provided metadata from each .json file
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



#### Process a subset of samples

To process a subset of samples, use

```bash
cytoprocess --sample 'name_of_cyz_file' command path/to/project
```
which processes this single sample. Or
```bash
cytoprocess --sample '*foo*' command path/to/project
```
which process all samples whose name contains foo.

All commands will skip the processing of a given sample if the output is already present. To re-process and overwrite, use the `--force` option.

#### Define new metadata

For metadata and cytometric features extraction (`extract_meta` and `extract_cyto`), information from the json file needs to be curated and translated into EcoTaxa metadata columns. This is defined in the configuration file `my_project/config/config.yaml`. It contains `key: value` pairs of the form `json.fields.item.name: ecotaxa_name`. To get the list of possible json fields, use the `--list` (or `-l`) option for `extract_meta` or `extract_cyto`; it will write a text file in `config` with all possibilities. You can then copy-paste them to `config/config.yaml`.

Even with all these fields available, the CytoSense does not record some relevant metadata such as latitude, longitude, and date of collection of each sample, which EcoTaxa needs to filter the data or export it to other data bases. You should provide such fields manually by editing the `meta/samples.csv` file.

If you change this metadata or the mapping of fields in `config.yaml` and want to reimport the modified .tsv files on EcoTaxa, you can do so with

```bash
# re-generate the .tsv files with the corrected metadata
cytoprocess prepare --force path/to/project
# re-upload the .tsv only and use "Update metadata" mode
cytoprocess upload --update path/to/project
```

#### Pre-classify the images

To predict the classification of images outside of EcoTaxa, you need to define a function with the signature `def my_fun(paths, features)`, either in a custom package that can be found by python with `import` or, simply, in a file (e.g. `my_model.py`). Then you can call

```bash
cytoprocess predict --model my_model.py::my_fun /path/to/project
```

For each sample, this will pass two arguments to your function:
- `paths`: a list of absolute paths to the images
- `features`: a pandas DataFrame with as many rows as there are images and cytometric + image features as columns.

Your function should return a DataFrame (or a dictionary that can be converted to one) with rows matching the input images (same number, same order) and at least one column called 'annotation_category' containing the predicted EcoTaxa category name for each image.

NB: If you use deep learning approaches, remember that the images all have a 31 px high scale bar at the bottom which should be removed before processing the image (typically, at the very beginning of the your data loader).

### Cleaning up after processing

Because everything is stored in the EcoTaxa .zip files and can be re-generated from the .cyz files, you may want to remove the intermediate files, in work, as well as old log files, to reclaim disk space. For example, to remove intermediate files and log files older than 20 days

```bash
cytoprocess clean --older-than 20 path/to/project
```

## Commands reference

Here are all cytoprocess commands

```
Usage: cytoprocess [OPTIONS] COMMAND [ARGS]...

  CytoProcess command line interface

  CytoProcess is a tool to process CytoSense images and upload them to EcoTaxa.
  It uses the concept of "project" to organise the data and metadata. It
  provides commands to create a project, convert raw files, extract metadata and
  features, summarise pulse shapes, extract images, optionally predict their
  classification, prepare files for EcoTaxa, and upload them.

Options:
  -d, --debug        Show debugging messages.
  -s, --sample TEXT  Limit processing to the sample(s) matching the given
                     string, including globing patterns (e.g. 'sample_123' to
                     process only the sample called exactly that or '*2025* to
                     process all samples with '2025' in their name).
  --help             Show this message and exit.

Commands:
  install           Install dependency: Cyz2Json converter.
  create            Create a new CytoProcess project directory.
  list              List samples and create/update meta/samples.csv.
  convert           Convert .cyz files to .json format.
  extract_meta      Extract instrument metadata from .json files.
  extract_cyto      Extract cytometric features from .json files.
  summarise_pulses  Summarise pulse shapes.
  extract_images    Extract images from .json files.
  prepare           Prepare .tsv and images for EcoTaxa.
  upload            Upload files to EcoTaxa.
  all               Run all steps from convert to upload in sequence.
  status            Show per-sample processing status.
  clean             Remove intermediate files in the project.
  predict           Run a user-provided model to predict classifications.

```

```

Usage: cytoprocess install [OPTIONS]

  Install dependency: Cyz2Json converter.

  This tool is required to convert .cyz files in a readable .json format. It is
  distributed from https://github.com/OBAMANEXT/cyz2json. This command installs
  the latest release automatically.

Options:
  -f, --force  Force (re)installation of the latest release even if Cyz2Json
               already exists.
  --help       Show this message and exit.

```

```

Usage: cytoprocess create [OPTIONS] PROJECT

  Create a new CytoProcess project directory.

Options:
  --help  Show this message and exit.

```

```

Usage: cytoprocess list [OPTIONS] PROJECT

  List samples and create/update meta/samples.csv.

  Run this after creating the project and after adding new .cyz files to it.
  Once run, the file meta/samples.csv should be edited to add metadata for each
  sample. The default metadata fields are very relevant for EcoTaxa (location,
  time, etc.).

Options:
  -e, --extra-fields TEXT  Comma-separated list of extra fields to add as
                           columns in samples.csv.
  --help                   Show this message and exit.

```

```

Usage: cytoprocess convert [OPTIONS] PROJECT

  Convert .cyz files to .json format.

Options:
  -f, --force  Force conversion even if .json files already exist.
  --help       Show this message and exit.

```

```

Usage: cytoprocess extract_meta [OPTIONS] PROJECT

  Extract instrument metadata from .json files.

  These are metadata fields stored in the .json by the CytoSense itself. They
  are useful to describe the acquisition of the samples.

  The names of the fields can by found by using the `--list` option, and should
  then be mapped to EcoTaxa metadata columns in config.xml.

Options:
  -l, --list   List all metadata items found in the .json file(s) instead of
               extracting some of them.
  -f, --force  Force extraction even if output files already exist.
  --help       Show this message and exit.

```

```

Usage: cytoprocess extract_cyto [OPTIONS] PROJECT

  Extract cytometric features from .json files.

  These correspond to what is traditionally called the "listmode" files: they
  are summaries of the pulse shape per channel for each object (maximum value,
  average value, etc.). Some can be directly informative biologically and all
  can be used by machine learning algorithms to predict classifications.

  Similarly, to the metadata fields, the names of the cytometric features can be
  found by using the `--list` option, and should then be mapped to EcoTaxa
  feature columns in config.xml.

Options:
  -l, --list   List all cytometric fields paths found in the .json file(s)
               instead of extracting some of them.
  -f, --force  Force extraction even if output files already exist.
  --help       Show this message and exit.

```

```

Usage: cytoprocess summarise_pulses [OPTIONS] PROJECT

  Summarise pulse shapes.

  The pulse shapes for each particle are standardised between 0 and 1 and then
  approximated by a polynomial of degree `n_poly` (default 10). The coefficients
  of the polynomial are then used as features in EcoTaxa. This is a way to
  summarise the pulse shapes while keeping their general form, which can be
  informative for classification.

  In addition, a plot of the standardised pulse shape is created. This plot is
  uploaded to EcoTaxa as the third image of each object.

Options:
  -n, --n-poly INTEGER     Number of polynomial coefficients
  -f, --force              Force processing even if output files already exist.
  -m, --max-cores INTEGER  Maximum number of CPU cores to use for parallel
                           processing.
  --help                   Show this message and exit.

```

```

Usage: cytoprocess extract_images [OPTIONS] PROJECT

  Extract images from .json files.

  Extract the images from the .json files and segments the main object in each.
  It stores a file for the image and for the mask, which are both uploaded to
  EcoTaxa.

  Some usual features are measured on the segmented object (area, perimeter,
  etc.), which are added to the features extracted from the pulse shapes and can
  be used for classification or biological interpretation.

Options:
  -f, --force              Force extraction even if output files already exist.
  -m, --max-cores INTEGER  Maximum number of CPU cores to use for parallel
                           processing.
  --help                   Show this message and exit.

```

```

Usage: cytoprocess prepare [OPTIONS] PROJECT

  Prepare .tsv and images for EcoTaxa.

  Create a .zip archive in the `ecotaxa` folder with: (1) the .tsv file with the
  metadata and features for each object and (2) three images per object (image,
  mask, pulse plot), for each sample.

Options:
  -f, --force  Force preparation even if output files already exist.
  --help       Show this message and exit.

```

```

Usage: cytoprocess upload [OPTIONS] PROJECT

  Upload files to EcoTaxa.

  The .zip files prepared are uploaded and then imported into an EcoTaxa
  project, configured in config.xml.

  If the `--update` flag is used, only the metadata of existing samples is
  updated, without re-uploading the images. This is useful to update the
  metadata after editing samples.csv: it only requires to re-run the `prepare`
  step and then `upload --update`.

Options:
  -u, --username TEXT  EcoTaxa email address.
  -p, --password TEXT  EcoTaxa password.
  --update             Only update the metadata for existing samples.
  --help               Show this message and exit.

```

```

Usage: cytoprocess all [OPTIONS] PROJECT

  Run all steps from convert to upload in sequence.

Options:
  -f, --force              Force processing even if output already exists.
  -n, --n-poly INTEGER     Number of polynomial coefficients.
  -m, --max-cores INTEGER  Maximum number of CPU cores to use for parallel
                           processing.
  --help                   Show this message and exit.

```

```

Usage: cytoprocess status [OPTIONS] PROJECT

  Show per-sample processing status.

Options:
  -w, --width INTEGER  Width of the sample ID display (truncated with ellipsis
                       if too long).
  --help               Show this message and exit.

```

```

Usage: cytoprocess clean [OPTIONS] PROJECT

  Remove intermediate files in the project.

  Remove the `work` directory: everything in it can be re-generated by re-
  running the commands and the relevant content is stored in the .zip files in
  `ecotaxa`.

  Optionnally, log files older than a certain number of days can also be
  removed.

Options:
  -o, --older-than INTEGER  Remove log files older than this many days (by
                            default, do not remove anything).
  --help                    Show this message and exit.

```

```

Usage: cytoprocess predict [OPTIONS] PROJECT

  Run a user-provided model to predict classifications.

  The function should accept two arguments:
  1. paths: a list of absolute paths to the images,
  2. features: a DataFrame with one row per image and cytometric + image
               features as columns (the cytometric features retained are
               defined in config.xml).

  It should return a DataFrame (or a dictionary that can be converted to one)
  with rows matching the input images (same number, same order) and at least one
  column called 'annotation_category' containing the predicted EcoTaxa category
  name for each image. Other columns can be added. All column names will be
  prepended with 'object_' before their import into EcoTaxa.

  NB: Images contain a 31 pixels-high scale bar at the bottom. It should be
  cropped out before feeding the image to a deep learning model.

Options:
  -m, --model TEXT  A function encapsulating the prediction model, specificed as
                    'path/to/model.py::func_name' or 'my_module.func_name'.
                    [required]
  -f, --force       Force re-prediction even if output already exists.
  --help            Show this message and exit.
```

RTFM ;-)

All this is accessible from cytoprocess by using `cytoprocess command --help`.

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
