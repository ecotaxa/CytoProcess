import csv
import json
import os
import subprocess
import sys
import argparse

"""
Tools to convert multiple cyz files to ecotaxa
using a tsv file to list the cyz files and the extra data to add,
with optional mapping of the extra data to the BioODV mapping


The header rows must have the following format:
- the first column is the colummn name
- the second column is the bioOBV name mapping
- the third column is the bioODV units mapping

Sample of the tsv file:
//,object_lat,SDN:P01::STRTXLAT,SDN:P06::UUUU
//,object_lon,SDN:P01::STRTXLON,SDN:P06::UUUU
//,object_date,SDN:P01::STRT8601,SDN:P06::UUUU
//,object_time,TIME,HH:MM
//,object_depth_min,DEEPMIN,METER
//,object_depth_max,DEEPMAX,METER
file,object_lat,object_lon,object_date,object_time,object_depth_min,object_depth_max
Deployment 1 2024-07-18 21h12.cyz,42,7.2,2019-04-17,10:00,10,100
"""

delimiter='\t'

def main(tsv_file, output_dir):
    try:
        # Make folder to store the extra_data JSON files
        os.makedirs(output_dir, exist_ok=True)

        with open(tsv_file, 'r', encoding='utf-8') as tsv:
            reader = csv.reader(tsv, delimiter=delimiter)
            header_mapping = []  # header lines

            column_headers = None  # The column headers

            for row in reader:
                if row[0] == '//': # header mapping line
                    header_mapping.append({
                        'column_name': row[1],
                        'object': row[2],
                        'units': row[3]
                    })
                    if ( row[1] == 'pulse_shape_file'):
                        pulse_shape_file = row[0]
                else:
                    # We are in the data part
                    if ( column_headers == None):
                        column_headers = row
                        print("Header:", column_headers)
                    else:
                        print("Header mapping:", header_mapping)
                        # here the data
                        print("DATA Row:", row)
                        working_dir = os.getcwd()
                        file_path = row[0]
                        file_name = os.path.basename(file_path)
                        json_file_name = os.path.splitext(file_name)[0] + ".json"
                        json_file_path = os.path.join(output_dir, json_file_name)
                        full_json_path = os.path.join(working_dir, json_file_path)
                        # build the json file
                        json_data = {}
                        for i, value in enumerate(row[1:], start=1):
                            print("Column:", column_headers[i])
                            # json_data[column_headers[i]] = {
                            #     'value': value 
                            # }
                                # Try to convert to number if possible
                            try:
                                numeric_value = float(value)
                                json_data[column_headers[i]] = {
                                    'value': numeric_value
                                }
                            except ValueError:
                                # Keep as string if not a number
                                json_data[column_headers[i]] = {
                                    'value': value
                                }
                                
                            # render the bioODV description optionally
                            # 
                            header = next((x for x in header_mapping if x['column_name'] == column_headers[i]), None)
                            print("Header:", header)
                            # if bioODV mapping for this column exists in header_mapping
                            if header != None:
                                json_data[column_headers[i]]['object'] = header['object']
                                json_data[column_headers[i]]['units'] = header['units']

                        # Save the JSON data to a file
                        with open(full_json_path, 'w', encoding='utf-8') as json_file:
                            print("Saving {json_file_path}")
                            json.dump(json_data, json_file, indent=4, ensure_ascii=False)

                        print(f"JSON file created: {json_file_path}")

                        call_pipeline_script(file_path, full_json_path)

    except Exception as e:
        print(f"Error: {e}")


def call_pipeline_script(file_path, json_file_path):
    """
        call convert.py with the cyzJSON file and the extra_data JSON file to generate the TSV file for Ecotaxa
    """
    print(f"Called convert.py with: {file_path} --extra {json_file_path}")
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_convert_path = os.path.join(script_dir, 'convert.py')
        subprocess.run([sys.executable, full_convert_path, file_path, '--extra', json_file_path], check=True)
        print(f"Called main.py with: {file_path} and {json_file_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error while calling main.py: {e}")

if __name__ == "__main__":
    output_dir = 'extra_data' # the folder to store the extra_data JSON files

    parser = argparse.ArgumentParser(description="Analyze a TSV file containing the list of cyz file with the extra data and the BioODV mapping")
    parser.add_argument("tsv_file", help="The path to the JSON file to analyze.")
    parser.add_argument("-d", "--delimiter", default="\t", help="Optional delimiter for the TSV file (default: tab)")
    args = parser.parse_args()

    tsv_file = args.tsv_file
    if args.delimiter != None:
        delimiter = args.delimiter

    main(tsv_file, output_dir)


