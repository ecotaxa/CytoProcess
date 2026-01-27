
from datetime import datetime
import numpy as np
import json, os, sys, shutil, argparse, base64


def remove_extension(value):
    """
    Function to remove the extension name from a file name.
    """
    print(f'remove_extension({value})')
    if value and isinstance(value, str):
        print(f'{os.path.splitext(value)[0]}')
        return os.path.splitext(value)[0]
    print("value")
    return value




def extract_date_utc(iso_datetime):
    """
    Extrait la date au format YYYYMMDD UTC à partir d'une chaîne ISO 8601.
    Convert an ISO 8601 datetime string to YYYYMMDD UTC format.
    """
    try:
        dt = datetime.fromisoformat(iso_datetime.rstrip("Z")).astimezone()  # Conversion vers UTC
        return dt.strftime("%Y%m%d UTC")
    except ValueError:
        return "INVALID_DATE"

def extract_time_utc(iso_datetime):
    """
    Extrait l'heure au format HHMMSS UTC à partir d'une chaîne ISO 8601.
    Convert an ISO 8601 datetime string to HHMMSS UTC format.
    """
    try:
        dt = datetime.fromisoformat(iso_datetime.rstrip("Z")).astimezone()  # Conversion vers UTC
        return dt.strftime("%H%M%S UTC")
    except ValueError:
        return "INVALID_TIME"


# def summarize_pulse_numpy(pulse_data_list, n_poly=10):
#     """
#     Summarizes a pulse shape using polynomial fitting with NumPy.

#     Args:
#         #pulse_data (np.ndarray): 1D NumPy array containing the pulse data.
#         pulse_data (List): array containing the pulse data.
#         n_poly (int): Degree of the polynomial fit.

#     Returns:
#         # np.ndarray: 1D NumPy array containing the polynomial coefficients.
#         List: array containing the polynomial coefficients.
#     """
#     pulse_data = np.array(pulse_data_list)
#     n = len(pulse_data)
#     x = np.linspace(1, n, n)  # Create x-values for the fit
#     poly = np.polynomial.polynomial.Polynomial.fit(x, pulse_data, deg=n_poly - 1)
#     coefficients = poly.convert().coef
#     return coefficients.tolist()

# def search_pulse_shapes(description):
#     """
#     Then in your mapping you can use it like:
#     {"name": "pulseShape_FWS", "type": "[t]", "transform": search_pulse_shapes("FWS")}
#     """
#     def search(value):
#         result = next((item for item in value if item['description'] == description), None)
#         if result:
#             # return result["values"]
#             return summarize_pulse_numpy(result["values"])

#         return None
#     return search


def extract_commit_version(s):
    """
    Extrait la version du commit de la chaîne CytoUSB.
    Exemple : "Commit: CytoUsb-v6.3.2.2-0-g2cf62c7b4" => "CytoUsb-v6.3.2.2-0-g2cf62c7b4"
    """
    import re
    match = re.search(r"Commit:\s*([^\s,]+)", s)
    if match:
        return match.group(1)
    return None

