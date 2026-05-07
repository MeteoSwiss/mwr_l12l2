from mwr_l12l2.errors import MWRDataError
import numpy as np
from metpy import calc
from metpy.units import units


class AtmosphericConstants:
    """
    Class containing atmospheric constants and parameters used in the retrieval.
    This should not changed except in case standard values are updated or if we want to implement a more complex atmospheric model in the future.
    """
    P0 = 1013.25  # Sea level standard atmospheric pressure in hPa
    T0 = 288.15   # Sea level standard temperature in K
    TK = 273.15    # Conversion from Celsius to Kelvin
    L = 0.0065    # Temperature lapse rate in K/m
    R = 8.31447   # Universal gas constant in J/(mol*K)
    M = 0.0289644 # Molar mass of Earth's air in kg/mol
    g = 9.80665   # Gravitational acceleration in m/s^2
    
    TROPOPAUSE_HEIGHT = 12000  # Height of the tropopause in meters (approximate)
    
def calculate_pressure_from_std_atmosphere(altitude_m):
    """
    Calculate the station pressure based on the station altitude and a standard atmosphere.
    
    Parameters:
    altitude_m (float): Station altitude in meters.
    
    Returns:
    station_pressure_std_atm (float): Calculated station pressure in hPa based on standard atmosphere.
    station_psfc_min (float): Minimum allowed surface pressure for the station in hPa.
    station_psfc_max (float): Maximum allowed surface pressure for the station in hPa.
    """
    # Unpack constants
    P0 = AtmosphericConstants.P0
    T0 = AtmosphericConstants.T0
    L = AtmosphericConstants.L
    R = AtmosphericConstants.R
    M = AtmosphericConstants.M
    g = AtmosphericConstants.g

    # Calculate the station pressure using the barometric formula
    if altitude_m < AtmosphericConstants.TROPOPAUSE_HEIGHT and altitude_m >= 0:  # Troposphere
        station_pressure_std_atm = P0 * (1 - L * altitude_m / T0) ** (g * M / (R * L))
    else:
        raise MWRDataError(f"Altitude {altitude_m} m is negative or above the tropopause height, this code is not designed for such altitudes.")
        
    
    # Define reasonable limits for surface pressure based on typical Earth conditions
    station_psfc_min = 0.85 * station_pressure_std_atm  # Minimum allowed surface pressure in hPa, based on observed record low pressures
    station_psfc_max = 1.1 * station_pressure_std_atm  # Maximum allowed surface pressure in hPa, based on observed record high pressures
    
    return station_pressure_std_atm, station_psfc_min, station_psfc_max

def calculate_forecast_indice_from_metpy(data, indice):
    """
    Calculate forecast indice based on the retrieved variables in the data. 
    
    Note: all metpy function work on 1D profile -> we need to iterate over time dimension and apply the function to each profile.
    Note 2: all tempetature should be provided in °C
    
    Parameters:
    data (xarray.Dataset): Dataset containing the retrieved variables.
    indice (str): Name of the indice to calculate (e.g., 'k_index', 'tq_index', 'mdpi') as defined in metpy.calc.
    
    Returns:
    data (xarray.Dataset): Dataset with the calculated indices added as new variables.
    """
    # Initilialie with empty
    data[indice] =  (('time'), np.full(data.time.shape, np.nan))
    
    # Check if indice is implemented in metpy:
    for t, time in enumerate(data.time):
        try:
            data_t = data.sel(time=time)
            
            # extract useful profiles and attributes units:
            pressure = data_t['pressure'].data * units("hPa")
            temperature = data_t['temperature'].data * units("degC")
            dewpt = data_t['dewpt'].data * units("degC")
            
            # Calculate the indice using the appropriate variables from the dataset
            if indice == 'k_index':
                indice_values_t = calc.k_index(pressure, temperature, dewpt)
            elif indice == 'lifted_index':
                parcel_profile = calc.parcel_profile(pressure, temperature, dewpt)
                indice_values_t = calc.lifted_index(pressure, temperature, parcel_profile)
            elif indice == 'showalter_index':
                indice_values_t = calc.showalter_index(pressure, temperature, dewpt)
            elif indice == 'total_totals':
                indice_values_t = calc.total_totals_index(pressure, temperature, dewpt)
            else:
                raise NotImplementedError(f"Indice {indice} is not implemented in the MetPy.")
            
            data[indice][t] = indice_values_t
            
        except Exception as e:  # TODO: catch specific exceptions related to missing variables or units issues
            # If the indice is not implemented, return an empty 1D Dataarray along time to dataset with the NaN values
            pass
    
    return data


def calculate_derived_product(data, product_name):
    """
    Calculate a derived product based on the retrieved variables in the data.
    
    Parameters:
    data (xarray.Dataset): Dataset containing the retrieved variables.
    product_name (str): Name of the derived product to calculate.
    
    #TODO: add uncertainty calculations for derived forecast indices based on the uncertainties of the input variables 
    
    Returns:
    data (xarray.Dataset): Dataset with the calculated derived product added as a new variable.
    """
    if product_name in ['total_totals', 'k_index', 'tq_index', 'lifted_index']:
        data = calculate_forecast_indice_from_metpy(data, product_name)
        # 'showalter_index', 's_index', 'thompson_index', 'jefferson_index', 'fog_threat', 'mdpi'
    else:
        # If the product is not implemented, return an empty 1D Dataarray along time to dataset with the NaN values
        data[product_name] = (('time'), np.full(data.time.shape, np.nan))

    return data