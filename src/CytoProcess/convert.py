import os
import subprocess
import sys
from pathlib import Path
import json

# def get_cyz2json_path():
#     """Get the platform-specific path to cyz2json binary"""
#     package_dir = Path(__file__).parent
#     # bin_dir = package_dir / "bin"
#     bin_dir = package_dir
    
#     binary_name = "cyz2Json.exe" if sys.platform == "win32" else "Cyz2Json"
#     binary_path = bin_dir / binary_name
    
#     if not binary_path.exists():
#         raise FileNotFoundError(f"Could not find cyz2json binary at {binary_path}")
    
#     # if sys.platform != "win32":
#         # binary_path.chmod(0o755)
    
#     return str(binary_path)

def get_cyz2json_path():
    """
    Get the platform-specific path to cyz2json binary,
    checking multiple possible locations.
    """
    package_dir = Path(__file__).parent
    binary_name = "cyz2Json.exe" if sys.platform == "win32" else "Cyz2Json"
    
    # List of possible locations to check
    possible_locations = [
        package_dir / binary_name,           # Direct in package
        package_dir / "bin" / binary_name,   # In bin subdirectory
        package_dir / "lib" / binary_name    # In lib subdirectory
    ]
    
    # Check if the binary exists in any of the possible locations
    for location in possible_locations:
        if location.exists():
            # Make sure the binary is executable on Unix systems
            if sys.platform != "win32" and not os.access(str(location), os.X_OK):
                try:
                    location.chmod(0o755)
                except Exception as e:
                    print(f"Warning: Could not make {location} executable: {e}")
            
            return str(location)
    
    # If we get here, we couldn't find the binary
    raise FileNotFoundError(f"Could not find cyz2json binary in any of: {[str(loc) for loc in possible_locations]}")


# def create_default_extra_data(input_path):
#     """
#     Create a default extra_data.json file if none exists
    
#     Args:
#         input_file (Path): Path to the input .cyz file
#     Returns:
#         Path: Path to the extra data JSON file
#     """
#     extra_data = {
#         "cruise": "",
#         "ship": "",
#         "station": "",
#         "bottle": "",
#         "latitude": "",
#         "longitude": "",
#         "depth": ""
#     }
    
#     # extra_file = input_path.parent / 'extra_data.json'
#     if not extra_file.exists():
#         with open(extra_file, 'w') as f:
#             json.dump(extra_data, f, indent=2)
#         print(f"Created default extra_data.json at {extra_file}")
#         print("Please edit this file with your metadata before processing.")
#         sys.exit(0)
    
#     return extra_file

def process_file(input_file, extra_data): #, output_data):
    """
    Process a cytosense file through cyz2json and main.py
    
    Args:
        input_file (str): Path to the input .cyz file
        extra_data
        output_data
    """
    input_path = Path(input_file).resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    if not input_path.suffix.lower() == '.cyz':
        print("Error: Input file must have .cyz extension")
        sys.exit(1)
    
    # Get paths
    json_output = input_path.with_suffix('.json')
    # extra_data = create_default_extra_data(input_path)
    # extra_data = Path(extra_data).resolve()
    output_data = input_path.with_suffix('.tsv')
    cyz2json = get_cyz2json_path()

    print("json_output:",json_output)
    print("extra_data:",extra_data)
    print("output_data:",output_data)
    print("cyz2json:",cyz2json)
    
    # Convert .cyz to .json
    print(f"Converting {input_path.name} to JSON...")
    try:
        subprocess.run([cyz2json, str(input_path), '--output', str(json_output)], 
                      check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running cyz2json: {e}")
        sys.exit(1)
    
    # Run main.py with the generated JSON
    print("Processing with main.py...")
    try:
        # main_script = Path('/opt/CytoProcess_venv/bin/main.py')
        main_script = Path('main.py')
        python_exe = Path(sys.executable)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_main_path = os.path.join(script_dir, 'main.py')

        subprocess.run([
            str(python_exe),

            str(full_main_path),
            str(json_output),
            '--extra',
            str(extra_data),
            # '--output',
            # str(output_data)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running main.py: {e}")
        sys.exit(1)


def is_absolute_windows(path):
    """Determines if a path is absolute on Windows."""
    return os.path.splitdrive(path)[0] != ""

def is_absolute_unix(path):
    """Determines if a path is absolute on Unix/Linux/macOS."""
    return path.startswith('/')

def is_absolute(path):
    """Determines if a path is absolute, depending on the operating system."""
    if os.name == 'nt':
        return is_absolute_windows(path)
    else:
        return is_absolute_unix(path)

def nb_args_expected():
    """Returns the number of arguments the script expect, depending on the OS use"""
    if os.name == 'nt':
        return 3
    else:
        return 4


def main_cli():
    """Command line interface entry point"""
    if len(sys.argv) != nb_args_expected():
        print("Usage: CytoProcess <input_cyz_file> --extra <extra_data.json>") # --output <output_data>")
        sys.exit(1)

    print("-- Pipeline --")

    local_path = os.getcwd()
    print("local_path")

    input_file = sys.argv[1]
    if not is_absolute(input_file):
        input_file = os.path.abspath(input_file)
    print("input_file:",input_file)

    # extra_file")
    extra_file_cmd = sys.argv[2]
    if ( extra_file_cmd != "--extra"):
        print("Error: --extra argument is missing")
        sys.exit(1)

    extra_file = sys.argv[3]
    if not is_absolute(extra_file):
        extra_file = os.path.abspath(extra_file)
    print("extra_file:",extra_file)


    # output_file 

    # process_file(sys.argv[1],sys.argv[2]) #,sys.argv[3])
    process_file(input_file, extra_file) #, output_file)
    print("Your files have been generated in:", local_path)

if __name__ == "__main__":
    main_cli()