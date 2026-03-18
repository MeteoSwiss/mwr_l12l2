from mwr_l12l2.errors import MWRDataError
import numpy as np

class AtmosphericConstants:
    """
    Class containing atmospheric constants and parameters used in the retrieval.
    This should not changed except in case standard values are updated or if we want to implement a more complex atmospheric model in the future.
    """
    P0 = 1013.25  # Sea level standard atmospheric pressure in hPa
    T0 = 288.15   # Sea level standard temperature in K
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

def calculate_derived_product(data, product_name):
    """
    Calculate a derived product based on the retrieved variables in the data.
    
    Parameters:
    data (xarray.Dataset): Dataset containing the retrieved variables.
    product_name (str): Name of the derived product to calculate.
    
    Returns:
    derived_product (xarray.DataArray): Calculated derived product or empty variables if the product is not implemented.
    """
    if product_name == 'test':
        pass
    else:
        # If the product is not implemented, return an empty 1D Dataarray along time to dataset with the NaN values
        data[product_name] = (('time'), np.full(data.time.shape, np.nan))

    return data[product_name] 