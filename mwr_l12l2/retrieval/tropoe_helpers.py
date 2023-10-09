import os.path
from subprocess import run

import numpy as np
import xarray as xr

from mwr_l12l2.utils.data_utils import set_encoding
from mwr_l12l2.utils.file_utils import abs_file_path, replace_path


def model_to_tropoe(model, station_altitude):
    """extract reference profile and uncertainties as well as surface data from ECMWF to files readable by TROPoe

    Args:
        model: instance of :class:`mwr_l12l2.model.ecmwf.interpret_ecmwf.ModelInterpreter` that with executed run()

    Returns:
        prof_data: :class:`xarray.Dataset` containing model profile data in a form writable to an input nc for TROPoe
        sfc_data: :class:`xarray.Dataset` containing model surface data in a form writable to an input nc for TROPoe
    """

    central_lat = model.fc.latitude.values[int(len(model.fc.latitude) / 2)]
    central_lon = model.fc.longitude.values[int(len(model.fc.latitude) / 2)]

    height_agl = model.z_ref-station_altitude
    id_station_alt = height_agl[0,:]>0
        
    time_encoding = {'units': 'seconds since 1970-01-01', 'calendar': 'standard'}

    # prof_data_specs = xr.Dataset(
    #     data_vars = dict(
    #         time_offset=(['time'], model.time_ref),
    #         height=([])
    #     )
    # )
    prof_data_specs = {'base_time': dict(dims=(), data=np.datetime64('1970-01-01', 'ns')),
                       'time_offset': dict(dims='time', data=model.time_ref),
                       'lat': dict(dims=(), data=central_lat,
                                   attrs={'units': 'degrees_north'}),
                       'lon': dict(dims=(), data=central_lon,
                                   attrs={'units': 'degrees_east'}),
                       'height': dict(dims='height', data=np.mean(height_agl[:,id_station_alt], axis=0) / 1e3,
                                      attrs={'long_name': 'Height above ground level', 'units': 'km'}),
                       'temperature': dict(dims=('time', 'height'), data=model.t_ref[:,id_station_alt] - 273.15,
                                           attrs={'units': 'Celsius'}),
                       'sigma_temperature': dict(dims=('time', 'height'), data=model.t_err[:,id_station_alt],
                                                 attrs={'units': 'Celsius'}),
                       'waterVapor': dict(dims=('time', 'height'), data=model.q_ref[:,id_station_alt] * 1e3,
                                          attrs={'units': 'g/kg'}),
                       'sigma_waterVapor': dict(dims=('time', 'height'), data=model.q_err[:,id_station_alt] * 1e3,
                                                attrs={'units': 'g/kg'}),
                       }

    prof_data_attrs = {'model': 'reference profile and uncertainties extracted from ECMWF operational forecast'}

    sfc_data_specs = {'base_time': dict(dims=(), data=np.datetime64('1970-01-01', 'ns')),
                      'time_offset': dict(dims='time', data=model.time_ref),
                      'lat': dict(dims=(), data=central_lat,
                                  attrs={'units': 'degrees_north'}),
                      'lon': dict(dims=(), data=central_lon,
                                  attrs={'units': 'degrees_east'}),
                      'pres': dict(dims=('time'), data=model.p_ref[:,id_station_alt][:,-1]/ 1e2,
                                  attrs={'units': 'hPa'}),
                      'height': dict(dims='time', data=height_agl[:,id_station_alt][:,-1] / 1e3,
                                     attrs={'long_name': 'Height above ground level', 'units': 'km'}),
                      'temp': dict(dims=('time'), data=model.t_ref[:,id_station_alt][:,-1] - 273.15,
                                          attrs={'units': 'Celsius'}),
                      'rh': dict(dims=('time'), data=model.rh[:,id_station_alt][:,-1]*1e2,
                                         attrs={'units': '%'}),
                      }
    # TODO: important! and easy... instead of just taking lowest altitude interp/extrapolate to station_altitude
    # instead. use log for pressure
    sfc_data_attrs = {'model': 'surface quantities and uncertainties extracted from ECMWF operational forecast'}
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


def run_tropoe(data_path, date, start_hour, end_hour, vip_file, apriori_file,
               data_mountpoint='/data', tropoe_img='davidturner53/tropoe', tmp_path='mwr_l12l2/retrieval/tmp',
               verbosity=1):
    """Run TROPoe container using podman for one specific retrieval

    Args:
        data_path: path that will be mounted to /data inside the container. Absolute path or relative to project dir
        date: date for which retrieval shall be executed. For now retrievals cannot encompass more than one day.
            Make sure that it is of type :class:`datetime.datetime` or a string of type 'yyyymmdd'. Alternatively you
            can pass 0 or '0' to let TROPoe print back the vip-file parameter options.
        start_hour: hour of the day defining the start time of the retrieval period. Can be a float, int or string.
        end_hour: hour of the day defining the end time of the retrieval period. Can be a float, int or string.
        vip_file: path to vip file relative to :obj:`data_path` or packaged inside container if matching 'prior.*'
        apriori_file:  path to a-priori file relative to :obj:`data_path`
        data_mountpoint (optional): where the data path will be mounted
        tropoe_img (optional): reference of TROPoe container image to use. Will take latest available by default
        tmp_path (optional): tmp path that will be mounted to /tmp inside the container. Uses a dummy folder by default
        verbosity (optional): verbosity level of TROPoe. Defaults to 1
    """

    # generate date string. Accept datetime.datetime and strings/integers (for special calls, e.g. 0 for vip docs)
    try:
        date_str = date.strftime('%Y%m%d')
    except AttributeError:
        date_str = '{}'.format(date)  # format to handle also integer input

    # map outside files into container
    vip_fullpath = replace_path(vip_file, data_path, data_mountpoint)
    if apriori_file[:6] == 'prior.':
        apriori_fullpath = apriori_file
    else:
        apriori_fullpath = replace_path(apriori_file, data_path, data_mountpoint)

    # construct cmd for subprocess
    cmd = ['podman', 'run', '-i', '-u', 'root', '--rm',
           '-v', '{}:{}'.format(abs_file_path(data_path), data_mountpoint),  # map the data path inside the container
           '-v', '{}:/tmp2'.format(abs_file_path(tmp_path)),  # map the tmp path to /tmp2 (for debug only)
           '-e', 'yyyymmdd=' + date_str,
           '-e', 'shour={}'.format(start_hour),
           '-e', 'ehour={}'.format(end_hour),
           '-e', 'vfile=' + vip_fullpath,  # path inside container, e.g. relative to dir mapped to /data
           '-e', 'pfile=' + apriori_fullpath,  # path inside container, e.g. relative to dir mapped to /data
           '-e', 'verbose={}'.format(verbosity),
           tropoe_img]
    run(cmd)


if __name__ == '__main__':
    run_tropoe('mwr_l12l2/data', 0, 'dummy/vip.txt', 'dummy/Xa_Sa.Lindenberg.55level.08.cdf')
