
# Tools to convert metadata spreadsheet into code

## Manual convertion
I converted the "features_metadata_cytometry - SSLAMM_micro_setdef_CS101 - collab" spreadsheet file into csv file.

## Determine type of rows
Then I used the python scrypt addType2CVS.py to add a column in the csv file. The columnn named type is filled with some Ecotaxa string type [t] for text or [f] for number, to better better generation code i use extended code (that are not defined in Ecotaxa) like [d] or [b] that are for date and boolean respectively. The type are determine from the column named "example_value".
That column is important to the following processing then at this point you could verify if data is correct by checking the values of the columns.
The script addType2CVS.py generate the file : features_metadata_cytometry - SSLAMM_micro_setdef_CS101 - collab update.tmp.csv

Be careful, if you relauch the script data will be overwritten.

## Generate some new columns

I use the python scrypt update_tsv.py to add and fill new columns in the csv file.
The column "name"  of the ecotaxa column data are determined from "path" column.
The column "transform" is the column to determine if we need to call some functions to transform raw data. Its value is determine from the column "type".
I added 3 optional columns for manage the bioODV relation. The column are:
+ The column "bioODV.name" is the name we will use in Ecotaxa, the idea is to use same name in all Ecotaxa project. If the BioODV columns are not filled, script will use the column "name"
+ The column "bioODV.object" is the BioODV official name
+ The column "bioODV.units" is the unit of measurement following the BioODV convention
The script update_tsv.py generate the file : features_metadata_cytometry - SSLAMM_micro_setdef_CS101 - collab update.csv

Before next step, you could change all the data. change name, choose transform function if need, fill bioODV columns. You will need to add your function in src/CytoProcess/transform_function.py file.

Be careful, if you relauch the script data will be overwritten.
Be careful, if you relauch the script data will be overwritten.

## generate code for python

The script generate_mapping.py is used to generate the mapping.py file.  mapping.py file will be use in the CytoProcess to convert your cyz file in ecotaxa tsv file.

## Update the pipeline

You need to manually copy mapping.py into src/CytoProcess folder.
At the point followed the intruction to rebuild your new pipeline version.


# Conclusion
At each step you could change the data to adapt to your wish
 but Be careful, if you relauch scripts data will be overwritten, then use git to keep track of changes. 