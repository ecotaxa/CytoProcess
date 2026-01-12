
import json, os, sys, shutil, argparse, base64
import numpy as np
import matplotlib.pyplot as plt
from zipfile import ZipFile
from PIL import Image
# from .transform_function import *
# from .mapping import column_mapping
# from cytosense_to_ecotaxa_pipeline.transform_function import *
# from cytosense_to_ecotaxa_pipeline.mapping import column_mapping

try:
    # Essayer d'abord l'importation relative (fonctionne lors du développement)
    from .transform_function import *
except ImportError:
    # Si ça échoue, essayer l'importation absolue (fonctionne après installation)
    from cytosense_to_ecotaxa_pipeline.transform_function import *

try:
    # Essayer d'abord l'importation relative (fonctionne lors du développement)
    from .mapping import column_mapping, particles_parameters, channel_parameters, particule_features
except ImportError:
    # Si ça échoue, essayer l'importation absolue (fonctionne après installation)
    from cytosense_to_ecotaxa_pipeline.mapping import column_mapping, particles_parameters, particule_features



###########################################################
# Cytosense to EcoTaxa conversion tool                    #
###########################################################

# --------------------------------------------------------
# Draw pulse shape images for each particle
# --------------------------------------------------------

bioODVHeader=False

# def remove_extension(value):
#     """
#     Function to remove the extension name from a file name.
#     """
#     if value and isinstance(value, str):
#         return os.path.splitext(value)[0]
#     return value

# Transformation pour les dates
# def transform_date(value):
#     if value and isinstance(value, str):
#         try:
#             return datetime.fromisoformat(value).strftime("%Y-%m-%d")
#         except ValueError:
#             return value  # Retourne la valeur brute si elle n'est pas au bon format
#     return value

# def transform_time(value):
#     if value and isinstance(value, str):
#         try:
#             return datetime.fromisoformat(value).strftime("%H:%M:%S")
#         except ValueError:
#             return value  # Retourne la valeur brute si elle n'est pas au bon format
#     return value

# def extract_date_utc(iso_datetime):
#     """
#     Extrait la date au format YYYYMMDD UTC à partir d'une chaîne ISO 8601.
#     Convert an ISO 8601 datetime string to YYYYMMDD UTC format.
#     """
#     try:
#         dt = datetime.fromisoformat(iso_datetime.rstrip("Z")).astimezone()  # Conversion vers UTC
#         return dt.strftime("%Y%m%d UTC")
#     except ValueError:
#         return "INVALID_DATE"

# def extract_time_utc(iso_datetime):
#     """
#     Extrait l'heure au format HHMMSS UTC à partir d'une chaîne ISO 8601.
#     Convert an ISO 8601 datetime string to HHMMSS UTC format.
#     """
#     try:
#         dt = datetime.fromisoformat(iso_datetime.rstrip("Z")).astimezone()  # Conversion vers UTC
#         return dt.strftime("%H%M%S UTC")
#     except ValueError:
#         return "INVALID_TIME"


# def search_Pulse_Shapes(value, description):
#     return next((item for item in value if item['description'] == description), None)

# def search_FWS(value):
#     result = search_Pulse_Shapes(value, "FWS")
#     return result["values"]

# moved to .transform_function
# def search_pulse_shapes(description):
#     """
#     Then in your mapping you can use it like:
#     {"name": "pulseShape_FWS", "type": "[t]", "transform": search_pulse_shapes("FWS")}
#     """
#     def search(value):
#         result = next((item for item in value if item['description'] == description), None)
#         if result:
#             return result["values"]
#         return None
#     return search

def search_pulse_shapes2(description, value):
    """
    Search in pulse value the section associated to description 
    and return its values
    """
    result = next((item for item in value if item['description'] == description), None)
    if result:
        return result["values"]
    return None

def draw_all_pulses_normalized(pulseShapes, image_path):
    """
    Dessine toutes les courbes de pulseShapes sur une même image, normalisées entre 0 et 1.
    """
    plt.figure(figsize=(10, 6))
    for pulse in pulseShapes:
        values = np.array(pulse["values"])
        if len(values) == 0:
            continue
        # Normalisation entre 0 et 1
        norm_values = (values - np.min(values)) / (np.max(values) - np.min(values)) if np.max(values) != np.min(values) else values
        plt.plot(norm_values, label=pulse["description"])
    plt.title("All pulse shapes (normalized)")
    plt.xlabel("Time")
    plt.ylabel("Normalized value")
    plt.legend()
    plt.tight_layout()
    plt.savefig(image_path)
    plt.close()

def image_particle2(particle_data):
    max_y = len(particle_data)
    max_x = 50

    a = np.zeros((max_y, max_x), dtype=np.uint8)

    y = 0
    for pulse_shape in particle_data:
        x = 0
        print(len(particle_data))

        for value in particle_data:
            if x >= max_x:
                break

            a[y, x] = value
            x = x + 1

        y = y + 1
    return a

def draw_pulse_shape_old(pulse_data,description,image_path):

    data = search_pulse_shapes2(description, pulse_data)

    a = image_particle(data)
    # Normalize to 0-1
    a = (a - np.min(a)) / (np.max(a) - np.min(a))

    a = a * (256 * 256 * 256 - 1)

    red = a // (256**2)
    green = (a // 256) % 256
    blue = a % 256

    rgb_image_array = np.stack((red, green, blue), axis=-1)

    # Convert the 3D array into an image using Pillow
    image = Image.fromarray(np.uint8(rgb_image_array))
    image.save(image_path)


def normalize_data(values):
    """Normalizes data to the range [0, 1] using min-max scaling."""
    return (values - np.min(values)) / (np.max(values) - np.min(values))

def draw_pulse_shape(pulse_data, description, image_path, normalize=True):
    """
    Draws a pulse shape image from pulse data and saves it.

    Args:
        pulse_data (list): List of pulse shape dictionaries.
        description (str): Description of the pulse shape to draw (e.g., "FWS").
        image_path (str): Path to save the image.
    """
    values = next((pulse["values"] for pulse in pulse_data if pulse["description"] == description), None)
    if values is None:
        print(f"Warning: No pulse shape found with description '{description}'. Skipping image creation.")
        return

    if normalize:
        values = normalize_data(values) # Normalize if requested

    x = range(len(values))
    fig, ax = plt.subplots(figsize=(10, 6))  # Adjust figure size as needed
    ax.plot(x, values, marker="o", linestyle="-", ms=0.1)  # Keep marker size small
    ax.set_title(f"{description}")
    ax.set_xlabel("Time")  # Add axis labels
    ax.set_ylabel("Value")
    plt.tight_layout()
    plt.savefig(image_path) # Save the figure to the specified path
    plt.close(fig) # Close the figure to free up resources




# def draw_pulse_shape__(pulse_data, description, image_path):
#     """
#     Draws a pulse shape image from pulse data and saves it.

#     Args:
#         pulse_data (list): List of pulse shape dictionaries.
#         description (str): Description of the pulse shape to draw (e.g., "FWS").
#         image_path (str): Path to save the image.
#     """
#     values = next((pulse["values"] for pulse in pulse_data if pulse["description"] == description), None)

#     if values is None:
#         print(f"Warning: No pulse shape found with description '{description}'. Skipping image creation.")
#         return  # Or raise an exception if this is an error condition.

#     max_x = len(values)  # Dynamic width based on pulse data
#     max_y = 1 # Constant height now

#     a = np.zeros((max_y, max_x), dtype=np.float32)
#     a[0, :] = values  # Populate the array with pulse data


#     # Normalize to 0-255 for 8-bit image
#     a = ((a - np.min(a)) / (np.max(a) - np.min(a)) * 255).astype(np.uint8)


#     # Create the grayscale image using Pillow
#     image = Image.fromarray(a, mode="L") # 'L' mode for grayscale.
#     image.save(image_path)



# def add_pulse_shapes(description):
#     """
#     Then in your mapping you can use it like:
#     {"name": "pulseShape_FWS", "type": "[t]", "transform": add_pulse_shapes("FWS")}
#     """
#     def add(value):
#         result = next((item for item in value if item['description'] == description), None)
#         if result:
#             result["values"].append(0)

#         draw_pulse_shape(value, path)
#         return value
#     return add


def extract_features(image):
    return []

def image_particle(pulse_data):
    max_y = len(pulse_data)
    max_x = 50

    a = np.zeros((max_y, max_x), dtype=np.uint8)

    y = 0
    for pulse_shape in pulse_data:
        x = 0
        # print(len(pulse_shape["values"]))

        for value in pulse_shape["values"]:
            if x >= max_x:
                break

            # a[y, x] = value
            a[y, x] = min(max(int(value), 0), 255)  # <-- Correction ici
            x = x + 1

        y = y + 1
    
    # a = np.clip(a, 0, 255)
    return a

def draw_pulse(pulse_particle, image_path):
    from PIL import Image

    a = image_particle(pulse_particle)
    # np.save(f"{output_dir}/{b}-{id}.npy", a)

    # Normalize to 0-1
    a = (a - np.min(a)) / (np.max(a) - np.min(a))

    a = a * (256 * 256 * 256 - 1)

    red = a // (256**2)
    green = (a // 256) % 256
    blue = a % 256

    rgb_image_array = np.stack((red, green, blue), axis=-1)

    # Convert the 3D array into an image using Pillow
    image = Image.fromarray(np.uint8(rgb_image_array))
    image.save(image_path)


def format_value(value):
    """
    Format values to clean TSV-friendly text 
    Clean the value, only one pair of quotes for text strings
    """
    if isinstance(value, str):
        cleaned_value = value.strip('"')  # Remove the double quote around the data
        return f'"{cleaned_value}"'
    return str(value)


def summarize_pulse_numpy(pulse_data_list, n_poly=10) -> list[float]:
    """
    Summarizes a pulse shape using polynomial fitting with NumPy.

    Args:
        #pulse_data (np.ndarray): 1D NumPy array containing the pulse data.
        pulse_data (List): array containing the pulse data.
        n_poly (int): Degree of the polynomial fit.

    Returns:
        # np.ndarray: 1D NumPy array containing the polynomial coefficients.
        List: array containing the polynomial coefficients.
    """
    pulse_data = np.array(pulse_data_list)
    n = len(pulse_data)
    x = np.linspace(1, n, n)  # Create x-values for the fit
    poly = np.polynomial.polynomial.Polynomial.fit(x, pulse_data, deg=n_poly - 1)
    coefficients = poly.convert().coef
    return coefficients.tolist()


# def transform_column_name(name):
#     """
#     Function pour transform dynamicately the column name
# """
#     return name.replace(".", "_").replace(" ", "_")

def gen_bioODV_header_from_extra(mapping, headers):
    """ Generate BioODV headers from extra_data.json content """
    print("BioODV header generating from extra data")
    for key, value in mapping.items():
        obj = value.get('object') if isinstance(value, dict) else None
        units = value.get('units') if isinstance(value, dict) else None
        if obj and units:
            row=f"<subject>{key}</subject>"
            row+=f"<object>{value['object']}</object>"
            row+=f"<units>{value['units']}</units>"
            headers.append(row)
    return headers

def gen_bioODV_header_from_mapping(mapping, headers):
    """ Generate BioODV headers from mapping file """
    print("BioODV header generating from mapping")
    for key, value in mapping.items():
        if 'bioodv' in value:
            row=f"<subject>{value['name']}</subject>"
            row+=f"<object>{value['bioodv']['object']}</object>"
            row+=f"<units>{value['bioodv']['units']}</units>"
            headers.append(row)
    return headers

def build_extra_data_array(extra_data):
    """
    Build an array of extra data values from the extra_data.json file.
    """
    row = []
    for value in extra_data.values():
        val = value['value'] if isinstance(value, dict) and 'value' in value else value
        row.append(format_value(val))
    return row

def build_mapping_array(data, column_mapping):
    row =[]
    for key, mapping in column_mapping.items():
        # print("Key:", key)
        # print("Mapping:", mapping)

        if "name" not in mapping or mapping["name"] is None:
            continue  # Ignore column with undefined name
        try:
            if "." in key:
                key_parts = key.split(".")
                current_obj = data
                for part in key_parts:
                    star = part.split("*")
                    # bracket = part.split("[")
                    if len(star) > 1: part = star[0]
                    # if len(bracket) > 1: 
                    #     part = bracket[0]
                    #     if part == "particles":
                    #         current_obj = particle
                    # else:
                    current_obj = current_obj.get(part, {})

                value = current_obj if current_obj != {} else None
            else:
                # value = particle.get(key, None)
                value = data.get(key, None)

            transform = mapping.get("transform")
            if transform:
                result = transform(value)
                # if isinstance(result, (list, tuple, np.ndarray)):
                #     for v in result:
                #         row.append(format_value(v))
                # else:
                if result is not None:
                    row.append(format_value(result))
                else:
                    row.append( "NaN" if mapping["type"] == "[f]" else "" )
            else:
                row.append(format_value(value))
        except Exception:
            # row.append("ERROR")
            row.append( "NaN" if mapping["type"] == "[f]" else "" )
    return row

# def make_row(particle, data, image_file, img_rank, column_mapping, extra_data, polynomial_fits=[]):
def make_row(data, image_file, img_rank, object_id, features, extra_data, polynomial_fits=[]):
    """ Build one TSV row per particle """
    row = [image_file, img_rank, object_id]
    # for value in extra_data.values():
    #     val = value['value'] if isinstance(value, dict) and 'value' in value else value
    #     row.append(format_value(val))
    row.extend(extra_data)

    # for key, mapping in column_mapping.items():
    #     # print("Key:", key)
    #     # print("Mapping:", mapping)

    #     if "name" not in mapping or mapping["name"] is None:
    #         continue  # Ignore column with undefined name
    #     try:
    #         if "." in key:
    #             key_parts = key.split(".")
    #             current_obj = data
    #             for part in key_parts:
    #                 star = part.split("*")
    #                 bracket = part.split("[")
    #                 if len(star) > 1: part = star[0]
    #                 if len(bracket) > 1: 
    #                     part = bracket[0]
    #                     if part == "particles":
    #                         current_obj = particle
    #                 else:
    #                     current_obj = current_obj.get(part, {})
    #             value = current_obj if current_obj != {} else None
    #         else:
    #             value = particle.get(key, None)

    #         transform = mapping.get("transform")
    #         if transform:
    #             result = transform(value)
    #             if isinstance(result, (list, tuple, np.ndarray)):
    #                 for v in result:
    #                     row.append(format_value(v))
    #             else:
    #                 row.append(format_value(result))
    #         else:
    #             row.append(format_value(value))
    #     except Exception:
    #         # row.append("ERROR")
    #         row.append( "NaN" if mapping["type"] == "[f]" else "" )
    row.extend(data)
    row.extend(features)

    row.extend(polynomial_fits)  # Add polynomial fits to the row
    return row

def getChannels(channels):
    """
    Extracts channel information from the instrument data.
    Returns a list of channel descriptions.
    """
    channel_descriptions = []
    for channel in channels:
        description = channel.get("description", "")
        if description:
            channel_descriptions.append(description)
    return channel_descriptions

def define_particules_columns(channel:str):
    """ define colomns for particles from channel description """
    columns = []
    if channel:
        channel_no_space = channel.replace(" ", "_")
        for particle_feature in particles_parameters:
            column_name = "object_" + channel_no_space + "_" + particle_feature
            columns.append(column_name)
    return columns

def get_particles_columns(channels) -> list: 
    """
    Extracts particle columns from the instrument channels.
    Returns a list of particle columns.
    """
    particle_columns = []
    for channel in channels:
        columns = define_particules_columns(channel)
        particle_columns.extend(columns)


    # Add the pulseShapes columns after all the particle columns
    for channel in channels:
        columns = []
        print(f"Processing channel: {channel}")
        column_name = f"{channel.replace(' ', '_')}"
        for index in range(1,11):
            columns.append(f"object_{column_name}_{index}")
        particle_columns.extend(columns)

    return particle_columns



def build_particles_parameters(channels:list[str], parameters):
    """
    Build the particle parameters from the channels and parameters.
    Returns a list of particle parameters.
    """
    particle_parameters = []
    for channel in channels:
        # search channel array that have description == channel
        parameterList = next((item for item in parameters if item['description'] == channel), None)
        if parameterList:
            for feature in particles_parameters:
                # print(f"Adding {feature} for channel {channel}")
                particle_parameters.append(parameterList.get(feature,"NaN"))            

    return particle_parameters

def build_polynomial_fits(channels:list[str], pulses):
    """
    Build polynomial fits for each particle in the particles list.
    Returns a list of polynomial fits.
    """
    from typing import Any
    polynomial_fits = []
    for channel in channels:
        pulse = next((item for item in pulses if item['description'] == channel), None)
        if pulse:
            # print(f"Processing channel: {channel}")
            values = pulse.get("values", [])
            if values:
                fit = summarize_pulse_numpy(values)
                polynomial_fits.extend(fit)
            else:
                print(f"Warning: No values found for channel '{channel}'. Skipping polynomial fit.")
        else:
            print(f"Warning: No pulse shape found with description '{channel}'. Skipping polynomial fit.")
    return polynomial_fits

def main(input_json, extra_data_file):
    # Loading the JSON files
    print("open:", input_json)
    print("extra:", extra_data_file)

    try:
        with open(input_json, "r") as f:
            data = json.load(f)
    except json.decoder.JSONDecodeError as e:
        print(f"Invalid JSON format in {input_json}")
        print("Error details:", str(e))
        print(f"Please check your cyz.json file.")
        sys.exit(1)

    try:
        with open(extra_data_file, "r") as f:
            extra_data = json.load(f)
    except json.decoder.JSONDecodeError as e:
        print(f"Invalid JSON format in {extra_data_file}")
        print("Error details:", str(e))
        print("Please check for trailing commas or other JSON syntax errors")
        sys.exit(1)

    # working_dir = os.getcwd()
    # output_images_dir = os.path.join(working_dir, "images")
    json_dir = os.path.dirname(os.path.abspath(input_json)) # save file aside the json file
    output_images_dir = os.path.join(json_dir, "images")
    print("output_images_dir:", output_images_dir)
    if os.path.exists(output_images_dir):
        shutil.rmtree(output_images_dir)
    os.makedirs(output_images_dir, exist_ok=True)

    output_tsv = os.path.join(output_images_dir, "ecotaxa_output.tsv")
    log_file = os.path.join(output_images_dir, "log.json")
    log_file = os.path.abspath(log_file) # make absolute path
    
    """
    Mapping dictionnary
    key is the json key
    value is an object to define how to store and transform the data for ecotaxa
        name: is the name of the column in ecotaxa
        type: is the type of the column in ecotaxa
        transform: is a function to transform the value before storing it, you can use a lambda function or a function to transform the value
        bioodv: the bioODV object
          bioodv.subject: is tsv column name [NOT NEEDED] = value.name
          bioodv.object: is the SDN name
          bioodv.units: is the SDN units
    """
    # column_mapping = {
    #     "filename": {"name": "sample_id", "type": "[t]", "transform": remove_extension},
    #     "nb_images": {"name": "img_rank", "type": "[f]", "transform": lambda _: 1},
    #     "instrument.name": {"name": "instrument", "type": "[t]", "transform": None},
    #     "instrument.serialNumber": {"name": "serialnumber", "type": "[t]", "transform": None},
    # }




    # # Add les dynamics column FOR measurementSettings AND measurementResults features
    # dynamic_keys = ["measurementSettings", "measurementResults"]
    # for key in dynamic_keys:
    #     if key in data["instrument"]:
    #         for subkey, value in data["instrument"][key].items():
    #             column_name = transform_column_name(f"{key}.{subkey}")
    #             column_mapping[f"{key}.{subkey}"] = {
    #                 "name": column_name,
    #                 "type": "[t]" if isinstance(value, str) else "[f]",
    #                 "transform": None,
    #             }

    # # add the pulseShapes columns
    # pulse_shapes = data["instrument"]["channels"]
    # for channel in pulse_shapes:
    #     print(f"Processing channel: {channel['description']}")
    #     column_name = transform_column_name(f"pulseShape.{channel['description']}")
    #     print(f"Column name: {column_name}")
    #     column_mapping[f"pulseShape.{channel['description']}"] = {
    #         "name": column_name,
    #         "type": "[t]",
    #         "transform": None,
    #     }

    # Build the columns and types list
    bioODV_header = ["SDN_PARAMETER_MAPPING"]
    bioODV_header = gen_bioODV_header_from_mapping(column_mapping, bioODV_header)
    bioODV_header = gen_bioODV_header_from_extra(extra_data, bioODV_header)
    # print(bioODV_header)
    columns = ["img_file_name", "img_rank", "object_id"] + list(extra_data.keys())  # Add extra data at the begin of the tsv line
    types = ["[t]", "[f]", "[t]"] + ["[t]" if isinstance(val.get('value') if isinstance(val, dict) else val, str) else "[f]" for val in extra_data.values()]
    seen_columns = set(columns)# Avoid duplicates with extra_data

    print(f"Nombre total de clés dans column_mapping: {len(column_mapping)}")
    
    # build the particle parameters columns follow by the p rticle pulseShape columns
    channels = getChannels(data["instrument"]["channels"])
    particles_columns = get_particles_columns(channels)

    ignored_columns = []
    valid_columns = []

    for key, mapping in column_mapping.items():
        if "name" not in mapping or mapping["name"] is None:
            ignored_columns.append(key)
            continue  # Ignore column where name is undefined
        else:
            valid_columns.append(key)
        if mapping["name"] not in seen_columns:
            # if mapping["name"].startswith("particles[].pulseShapes"):
            #     print(f"Processing pulse column: {mapping['name']}")
            #     for i in range(1, 11):
            #         print("Adding column for pulse shape:", f"{mapping['name']}_{i}")
            #         columns.append(f"{mapping['name']}_{i}")
            #     types.extend([mapping["type"]] * 10)
            #     seen_columns.add(mapping["name"])
            # else:
                columns.append(mapping["name"])
                types.append(mapping["type"])
                seen_columns.add(mapping["name"])

    # add the features columns
    for feature in particule_features:
        if feature not in seen_columns:
            columns.append("object_" + feature)
            types.append("[f]")

    # Add the particle parameters & pulseShapes column types
    columns.extend(particles_columns)
    types.extend(["[f]"] * len(particles_columns))

    print(f"Colonnes ignorées ({len(ignored_columns)}): {ignored_columns[:5]}...")  # Affiche les 5 premières
    print(f"Colonnes valides ({len(valid_columns)}): {len(valid_columns)}")
    
    # Array to log particles without image
    missing_images = []

    # Building tsv lines
    rows = []
    files_in_zip = []

    constant_data = build_mapping_array(data, column_mapping)
    constant_extra_data = build_extra_data_array(extra_data)
    
    # A cleaning step to remove tabs, returns and newlines. For our .cyz file (at Cefas), "UvserRemarks" contained three lines. Those \n newlines broke the pipeline and created a tsv that ecotaxa would not accept. For now, only apply this check to text in the UserRemarks object
    name_idx = {m["name"]: i for i, m in enumerate([m for m in column_mapping.values() if m.get("name")])}
    if (idx := name_idx.get("object_UvserRemarks")) is not None:
       constant_data[idx] = f'"{constant_data[idx].strip("\"").replace("\r"," ").replace("\n"," ").replace("\t"," ")}"'
    
    for particle in data["particles"]:
        if not particle["hasImage"]:
            continue  # Ignore particles without image

        particle_id = particle["particleId"]
        print(f"\rProcessing particle: {particle_id}", end='', flush=True)
        pulseShapes = particle["pulseShapes"]
        # print("pulseShapes:", pulseShapes)
        image_data = next((img["base64"] for img in data["images"] if img["particleId"] == particle_id), None)
        if image_data:
            image_file = f"particle_{particle_id}.jpg"
            with open(os.path.join(output_images_dir, image_file), "wb") as img_file:
                img_file.write(base64.b64decode(image_data))
                files_in_zip.append(os.path.join(output_images_dir, image_file))

            features = extract_features(image_data)
        else:
            missing_images.append(particle_id)
            continue  # go to next particle

        pulse_shape_file =  f"pulse_shape_{particle_id}.jpg"
        pulse_shape_path = os.path.join(output_images_dir, pulse_shape_file)
        with open(pulse_shape_path, "wb") as img_file:
            # image_data = draw_pulse_shape(pulseShapes, "FWS", pulse_shape_path)
            # img_file.write(image_data)
            # draw_pulse(pulseShapes, pulse_shape_path)
            draw_all_pulses_normalized(pulseShapes, pulse_shape_path)
            files_in_zip.append(pulse_shape_path)
            # files_in_zip.append(pulse_shape_path)

        features_pulse_shapes = [0] * len(particule_features)

        particle_parameters = build_particles_parameters(channels, particle["parameters"])
        particle_polynomial_fits = build_polynomial_fits(channels, particle["pulseShapes"])

        #TODO: add columns defining polynom coefficents of the pulse shape
        # row.append(polynomial_fits)

        #TODO: add columns defining polynom coefficents of the pulse shape
        # pulse_data_list = article["pulseShapes"]
        # pulse_data_list = []
        # polynomial_fits = [1,2,3,4,5]
        # polynomial_fits = summarize_pulse_numpy(pulse_data_list) # []
        polynomial_fits = particle_parameters + particle_polynomial_fits



        # row = make_row(particle, data, image_file, 0, column_mapping, extra_data, polynomial_fits)
        row = make_row(constant_data, image_file, 0, particle_id, features, constant_extra_data, polynomial_fits)
        rows.append(row)
        # row = make_row(particle, data, pulse_shape_file, 1, column_mapping, extra_data, polynomial_fits)
        row = make_row(constant_data, pulse_shape_file, 1, particle_id, features_pulse_shapes, constant_extra_data, polynomial_fits)
        rows.append(row)

    print() # to invalid the progress bar

    # Write TSV file
    with open(output_tsv, "w", newline="") as tsv_file:

        # Write the bioODV header

        if bioODVHeader == True:
            for row in bioODV_header:
                # tsv_file.write("\t".join(row) + "\n")
                tsv_file.write("//" + row + "\n")

        # Write the TSV header
        tsv_file.write("\t".join(columns) + "\n")
        tsv_file.write("\t".join(types) + "\n")

        # Write the TSV data
        for row in rows:
            # print("Row:", row)
            # tsv_file.write("\t".join(row) + "\n")
            tsv_file.write("\t".join(str(item) for item in row) + "\n")

    files_in_zip.append(output_tsv)
    
    archive_filename = os.path.splitext(input_json)[0] + '.zip'

    with ZipFile(archive_filename, 'w') as zip_file:
        for file in files_in_zip:
            zip_file.write(file)
            # zip_file.write(file, arcname=os.path.basename(file))



    # with ZipFile('archive.zip', 'w') as zip_file:
    #     for root, dirs, files in os.walk(output_images_dir):
    #         for file in files:
    #             file_path = os.path.join(root, file)
    #             zip_file.write(file_path, arcname=os.path.basename(file_path))

    # Write the log file
    # with open(log_file, "w") as log:
    #     json.dump(missing_images, log, indent=4)

    print(f"Images saved in: {output_images_dir}")
    print(f"TSV file saved in: {output_tsv}")
    # print(f"Log des particules sans images : {log_file}")
    print("Zip archive created:", archive_filename)



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

def cli_main():
    print("-- main.py --")
    parser = argparse.ArgumentParser(description="Analyze JSON file to generate a folder containing the TSV file and the images.")
    parser.add_argument("input_json", help="The path to the JSON file to analyze.")
    parser.add_argument("--extra", required=True, help="The path to the JSON file containing the extra data. (at the moment name must be extra_data.json and aside the json file)")
    parser.add_argument("--bioODV", action="store_true", default=False, help="Add the bioODV headers to the TSV file.")
    args = parser.parse_args()
    input_json = args.input_json
    if not is_absolute(input_json):
        input_json = os.path.abspath(input_json)
    #print("input_file:", input_json)

    extra_file = args.extra
    if not is_absolute(extra_file):
        extra_file = os.path.abspath(extra_file)
    #print("extra_file:",extra_file)

    bioODVHeader = args.bioODV

    main(args.input_json, args.extra)

# Entry point for CLI mode
if __name__ == "__main__":
    cli_main()


