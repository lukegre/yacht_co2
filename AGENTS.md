# yacht CO2

A python package to process cO2 measurements from an underway CO2 sampling instrument installed on a Vendee Globe yacht (Oliver Heer). 


## Package Design

- Package management is done using `uv`
- The majority of processing happens in xarray, and pandas when required. 
- Scripts are easy to read and follow the style of the legacy code. Functions are well documented using numpy style docs. 
- The API allows access to each step of processing making diagnostics easy
- Logging is abundant, using loguru. Levels of logging range from: DEBUG, INFO, SUCCESS, WARNING
- Data is saved in netCDF or zarr2 or CSV

## Data

- CO2 measurments are stored as log files in expedition folders. 
- Remote sensing data needs to be fetched. 
	- Prioritize CMEMS for remote sensing. 
	- Use ERA5 for wind data to compute fluxes. 

## Desired output

a) For each folder that contains data, returns a merged time series. 
b) If requested, remote sensing products, such as SST and SSS, maps over the full period and spatial domain. e.g., if a folder contains data from 19.03.2024 to 30.03.2024 in the north atlantic, return maps for this full period. If satellite data are requested, a new merged time series is returned with collocated satellite data to the nearest pixel.
c) Videos of the output as a time series. 
d) interactive web-based platform to interact with the dataset. This includes maps with a time scrubber and associated time series. 


## Legacy code
Legacy code for an old, not-so-stable package exists in `docs/legacy_code`. Naming is straightforward and easy to understand. When possible, use this code. Make sure that processing is correct. 

Some other useful packages include pySeaFlux. 
