from subprocess import run

import numpy as np
import xarray as xr

from mwr_l12l2.utils.data_utils import set_encoding
from mwr_l12l2.utils.file_utils import abs_file_path


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


def run_tropoe(data_path, date, vip_file, apriori_file, tropoe_img='davidturner53/tropoe',
               tmp_path='mwr_l12l2/retrieval/tmp', verbosity=1):
    """Run TROPoe container using podman for one specific retrieval

    Args:
        data_path: path that will be mounted to /data inside the container. Absolute path or relative to project dir
        date: date for which retrieval shall be executed. For now retrievals cannot encompass more than one day.
            Make sure that it is of type :class:`datetime.datetime` or a string of type 'yyyymmdd'. Alternatively you
            can pass 0 or '0' to let TROPoe print back the vip-file parameter options.
        vip_file: path to vip file relative to :obj:`data_path`
        apriori_file:  path to a-priori file relative to :obj:`data_path`
        tropoe_img (optional): reference of TROPoe continer image to use. Will take latest available by default
        tmp_path (optional): tmp path that will be mounted to /tmp inside the container. Uses a dummy folder by default
        verbosity (optional): verbosity level of TROPoe. Defaults to 1
    """

    # generate date string. Accept datetime.datetime and strings/integers (for special calls, e.g. 0 for vip docs)
    try:
        date_str = date.strftime('%Y%m%d')
    except AttributeError:
        date_str = '{}'.format(date)  # format to handle also integer input

    cmd = ['podman', 'run', '-i', '-u', 'root', '--rm',
           '-v', '{}:/data'.format(abs_file_path(data_path)),  # map the data path to /data inside the container
           '-v', '{}:/tmp2'.format(abs_file_path(tmp_path)),  # map the tmp path to /tmp2 (for debug only)
           '-e', 'yyyymmdd=' + date_str,
           '-e', 'vfile=/data/' + vip_file,  # path inside container, e.g. relative to dir mapped to /data
           '-e', 'pfile=/data/' + apriori_file,  # path inside container, e.g. relative to dir mapped to /data
           '-e', 'shour=00',  # achieve time selection over input files, hence consider whole day here
           '-e', 'ehour=24',  # achieve time selection over input files, hence consider whole day here
           '-e', 'verbose={}'.format(verbosity),
           tropoe_img]
    run(cmd)


if __name__ == '__main__':
    run_tropoe('mwr_l12l2/data', 0, 'dummy/vip.txt', 'dummy/Xa_Sa.Lindenberg.55level.08.cdf')
