import numpy as np
import xarray as xr

from mwr_l12l2.utils.data_utils import set_encoding


def model_to_tropoe(model):
    """extract reference profile and uncertainties as well as surface data from ECMWF to files readable by TROPoe

    Args:
        model: instance of :class:`mwr_l12l2.model.ecmwf.interpret_ecmwf.ModelInterpreter` that with executed run()

    Returns:
        prof_data: :class:`xarray.Dataset` containing model profile data in a form writable to an input nc for TROPoe
        sfc_data: :class:`xarray.Dataset` containing model surface data in a form writable to an input nc for TROPoe
    """

    central_lat = model.fc.latitude.values[int(len(model.fc.latitude) / 2)]
    central_lon = model.fc.longitude.values[int(len(model.fc.latitude) / 2)]
    time_encoding = {'units': 'seconds since 1970-01-01', 'calendar': 'standard'}

    prof_data_specs = {'base_time': dict(dims=(), data=np.datetime64('1970-01-01', 'ns')),
                       'time_offset': dict(dims='time', data=model.time_ref),
                       'lat': dict(dims=(), data=central_lat,
                                   attrs={'units': 'degrees_north'}),
                       'lon': dict(dims=(), data=central_lon,
                                   attrs={'units': 'degrees_east'}),
                       'height': dict(dims='height', data=model.z_ref / 1e3,
                                      attrs={'long_name': 'Height above mean sea level', 'units': 'km'}),
                       'temperature': dict(dims=('time', 'height'), data=model.t_ref[np.newaxis, :] - 273.15,
                                           attrs={'units': 'Celsius'}),
                       'sigma_temperature': dict(dims=('time', 'height'), data=model.t_err[np.newaxis, :],
                                                 attrs={'units': 'Celsius'}),
                       'waterVapor': dict(dims=('time', 'height'), data=model.q_ref[np.newaxis, :] * 1e3,
                                          attrs={'units': 'g/kg'}),
                       'sigma_waterVapor': dict(dims=('time', 'height'), data=model.q_err[np.newaxis, :] * 1e3,
                                                attrs={'units': 'g/kg'}),
                       }

    prof_data_attrs = {'source': 'reference profile and uncertainties extracted from ECMWF operational forecast'}

    sfc_data_specs = {'base_time': dict(dims=(), data=np.datetime64('1970-01-01', 'ns')),
                      'time_offset': dict(dims='time', data=model.time_ref),
                      'lat': dict(dims=(), data=central_lat,
                                  attrs={'units': 'degrees_north'}),
                      'lon': dict(dims=(), data=central_lon,
                                  attrs={'units': 'degrees_east'}),
                      'height': dict(dims='height', data=model.z_ref[-1:] / 1e3,
                                     attrs={'long_name': 'Height above mean sea level', 'units': 'km'}),
                      'temperature': dict(dims=('time', 'height'), data=model.t_ref[np.newaxis, -1:] - 273.15,
                                          attrs={'units': 'Celsius'}),
                      'sigma_temperature': dict(dims=('time', 'height'), data=model.t_err[np.newaxis, -1:],
                                                attrs={'units': 'Celsius'}),
                      'waterVapor': dict(dims=('time', 'height'), data=model.q_ref[np.newaxis, -1:] * 1e3,
                                         attrs={'units': 'g/kg'}),
                      'sigma_waterVapor': dict(dims=('time', 'height'), data=model.q_err[np.newaxis, -1:] * 1e3,
                                               attrs={'units': 'g/kg'}),
                      }
    # TODO: important! and easy... instead of just taking lowest altitude interp/extrapolate to station_altitude
    # instead. use log for pressure
    sfc_data_attrs = {'source': 'surface quantities and uncertainties extracted from ECMWF operational forecast'}
    # TODO: add more detail on which ECMWF forecast is used to output file directly in main retrieval routine
    # (info cannot be found inside grib file). Might also want to add lat/lon area used.

    # construct datasets
    prof_data = xr.Dataset.from_dict(prof_data_specs)
    sfc_data = xr.Dataset.from_dict(sfc_data_specs)

    # add encodings and global attrs to datasets
    for ds in [prof_data, sfc_data]:  # common time encodings for all datasets
        ds = set_encoding(ds, ['base_time', 'time_offset'], time_encoding)
    prof_data.attrs = prof_data_attrs
    sfc_data.attrs = sfc_data_attrs

    return prof_data, sfc_data
