import pandas as pd
import numpy as np


def read_single_log_file(fname: str) -> dict:
    """
    Reads a log file and returns a dictionary containing the log data.

    Parameters:
    fname (str): The filename of the log file.

    Returns:
    dict: A dictionary containing the log data.
    """

    # Initialize an empty dictionary to store the log data
    raw = {"DATA": [], "NAME": [], "SENSOR": [], "UNIT": [], "OTHER": []}
    
    # Open the log file
    with open(fname, encoding='latin') as file:
        for line in file:
            # Remove leading and trailing whitespace and split the line into a list of strings
            cols = line.strip().split(',')
            # Remove the "@" symbol from the first element in the list
            cols[0] = cols[0].replace("@", "")
            
            # Check if the modified first element is a key in the raw dictionary
            if cols[0] in raw:
                # Convert the remaining elements in the cols list to a one-dimensional numpy array
                raw[cols[0]].append(np.array(cols).squeeze())
            else:
                # Append the entire cols list to the "OTHER" key in the raw dictionary
                raw["OTHER"].append(cols)
                
    # Process the log data stored in the raw dictionary
    for key in raw:
        length = len(raw[key])
        
        # If the list of values has length 1, replace the value with the single element
        if length == 1:
            raw[key] = raw[key][0]
        # If the list of values has length greater than 1, convert it to a numpy array with dtype "O"
        elif length > 1:
            raw[key] = np.array(raw[key], dtype="O")
    
    return raw



def process_raw_data_to_dataframe(data: np.ndarray, headers: list):
    """Processes raw data into a structured pandas DataFrame.

    Args:
        data (np.ndarray): The raw data to be processed.
        headers (list): List of column headers for the data.

    Returns:
        df (pd.DataFrame): The processed data in the form of a DataFrame.

    """
    
    # Prepare DataFrame from raw data with given column headers
    df = pd.DataFrame(data, columns=headers)
    
    # Rename 'Status' and 'STATUS' columns to 'status' and 'sampling_phase' respectively
    df = df.rename(columns=dict(Status='status', STATUS='sampling_phase'), errors='raise')

    # Combine 'DATE' and 'TIME' columns to create a 'datetime' column
    df = df.assign(datetime=lambda x: pd.to_datetime(x.DATE + " " + x.TIME))
    
    # Modify column headers: to lower case, replace '.' and '/' with '_'
    df = df.rename(columns=lambda s: s.lower().replace('.', '_').replace('/', '_'))
    
    # Remove redundant columns - 'date', 'time', 'name'
    df = df.drop(columns=['date', 'time', 'name'])
    
    # Set 'datetime' as the index of the DataFrame
    df = df.set_index(["datetime"])

    # Attempt to convert columns to floats where possible
    df = df.apply(pd.to_numeric, errors='coerce')
    
    # Assign new coordinates with correct format to 'lat' and 'lon' columns
    df = df.assign(lat=lambda x: fix_coord(x.latitude), 
                   lon=lambda x: fix_coord(x.longitude))

    return df



def fix_coord(DDMMdec: pd.Series) -> pd.Series:
    """
    Convert coordinates from DDMM.dec format to decimal degree format.
    
    This function takes a pandas Series containing coordinates in the DDMM.dec
    format and converts them to the more common decimal degree format.
    
    DDMM.dec format is a compact representation of geographic coordinates, where:
    
    - DD represents the degrees of the coordinate.
    - MM represents the decimal minutes of the coordinate.
    - 'dec' indicates that the minutes are in decimal form.
    
    The conversion involves the following steps:
    
    1. Convert DDMMdec values to float and normalize by dividing by 100.
    2. Determine the sign (positive or negative) of the coordinates.
    3. Calculate the degrees and decimal minutes components.
    4. Combine degrees and decimal minutes to calculate the fixed coordinates 
       in decimal degree format.
    
    Parameters:
        DDMMdec (pd.Series): A pandas Series containing coordinates in DDMM.dec format.
        
    Returns:
        pd.Series: A pandas Series containing coordinates in decimal degree format.
    """
    
    # Convert DDMMdec to float and normalize (convert to degrees)
    DDMMdec = DDMMdec.astype(float)
    DDMMdec /= 100.
    
    # Determine the sign of the coordinates (positive or negative)
    sign = np.sign(DDMMdec)
    
    # Calculate degrees and decimal minutes
    DDMMdec = DDMMdec.abs()
    deg = DDMMdec // 1
    min = (DDMMdec - deg) / .6
    
    # Calculate the fixed coordinates in decimal degree format
    fixed = (deg + min) * sign
    
    return fixed


def read_mflog(flist_or_str) -> pd.DataFrame:
    from glob import glob
    if isinstance(flist_or_str, str):
        flist_or_str = glob(flist_or_str)
    
    df_all = []
    for fname in flist_or_str:
        raw = read_single_log_file(fname)
        if raw['DATA'].ndim == 1:
            continue
        df = process_raw_data_to_dataframe(raw['DATA'], raw['NAME'])
        df_all += df,
    
    df_all = pd.concat(df_all)
    for key in df_all:
        df_all[key] = df_all[key].astype(float, errors='ignore')
    return df_all


phases = {
    1: "Span 1 calibration",
    2: "Zero CO2 calibration",
    4: "Standby",
    5: "Operate (sea analysis)",
    15: "Span 2 calibration",
    18: "Reference gas measurement",
    19: "Warmup",
    21: "Operate StandBy (water pump active, gas pump stop)",
    22: "Air measurement",
}
