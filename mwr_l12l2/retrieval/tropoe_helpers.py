import os.path
import subprocess

import numpy as np
import xarray as xr

from mwr_l12l2.utils.data_utils import set_encoding
from mwr_l12l2.utils.file_utils import abs_file_path, replace_path
from mwr_l12l2.log import logger
from mwr_l12l2.errors import MWRConfigError
from mwr_l12l2.utils.file_utils import dict_to_file

def model_to_tropoe(model, station_altitude, OmB=False):
    """extract reference profile and uncertainties as well as surface data from ECMWF to files readable by TROPoe

    Args:
        model: instance of :class:`mwr_l12l2.model.ecmwf.interpret_ecmwf.ModelInterpreter` that with executed run()
        station_altitude: altitude of the station in meters above mean sea level
        OmB: bool, if True OmB is performed on temperature and humidity profiles -> needs a different formatting (?)

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
    if OmB:
        prof_data_specs = {'base_time': dict(dims=(), data=np.datetime64('1970-01-01', 'ns')),
                'time': dict(dims='time', data=np.flip(np.mean(height_agl[:,id_station_alt], axis=0)) / 1e3),
                #'time_offset': dict(dims='time', data=model.time_ref),
                # 'lat': dict(dims=(), data=central_lat,
                #             attrs={'units': 'degrees_north'}),
                # 'lon': dict(dims=(), data=central_lon,
                #             attrs={'units': 'degrees_east'}),
                'height': dict(dims='time', data=np.flip(np.mean(height_agl[:,id_station_alt], axis=0)) / 1e3,
                                attrs={'long_name': 'Height above ground level', 'units': 'km'}),
                'temperature': dict(dims='time', data=np.flip(model.t_ref[:,id_station_alt][0]) - 273.15,
                                    attrs={'units': 'Celsius'}),
                'pressure': dict(dims='time', data=np.flip(model.p_ref[:,id_station_alt][0])/ 1e2,
                                    attrs={'units': 'hPa'}),
                # 'sigma_temperature': dict(dims=('time', 'height'), data=model.t_err[:,id_station_alt],
                #                             attrs={'units': 'Celsius'}),
                'rh': dict(dims='time', data=np.flip(model.rh[:,id_station_alt][0]) * 1e2,
                                    attrs={'units': '%'}),
                }
    else:
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

    prof_data_attrs = {
        'model': 'reference profile and uncertainties extracted from ECMWF operational forecast',
        'gridpoint_lat': central_lat,
        'gridpoint_lon': central_lon,                       
    }

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
    #  instead. use log for pressure
    sfc_data_attrs = {
        'model': 'surface quantities and uncertainties extracted from ECMWF operational forecast',
        'gridpoint_lat': central_lat,
        'gridpoint_lon': central_lon,                       
    }
    # TODO: add more detail on which ECMWF forecast is used to output file directly in main retrieval routine
    #  (info cannot be found inside grib file). Might also want to add lat/lon area used.

    # construct datasets
    prof_data = xr.Dataset.from_dict(prof_data_specs)
    sfc_data = xr.Dataset.from_dict(sfc_data_specs)

    # add encodings and global attrs to datasets
    # Currently not working for OmB:
    if not OmB:
        for ds in [prof_data, sfc_data]:  # common time encodings for all datasets
            ds = set_encoding(ds, ['base_time', 'time_offset'], time_encoding)
    prof_data.attrs = prof_data_attrs
    sfc_data.attrs = sfc_data_attrs

    return prof_data, sfc_data


def build_vip_config(mwr_data, inst_conf, station_coords, has_surface_data, 
                    met_sfc_offset, tropoe_paths, output_basename, constants):
    """Build VIP configuration dictionary for TROPoe.
    
    Args:
        mwr_data: xarray Dataset with MWR observations
        inst_conf: Instrument configuration dictionary
        station_coords: dict with 'latitude', 'longitude', 'altitude'
        has_surface_data: bool indicating if complete surface data is available
        met_sfc_offset: Surface offset in meters (for model data)
        tropoe_paths: dict with path configuration:
            - 'mountpoint': TROPoe directory mountpoint
            - 'mwr_basename': MWR file basename
        output_basename: Output file basename
        constants: Constants class (e.g., RetrievalConstants)
        
    Returns:
        dict: VIP configuration parameters ready for writing
        int: Surface data type code (for setting ext_sfc_data_type)
        
    Raises:
        MWRConfigError: If channel configuration is invalid
    """
    ch_zenith = inst_conf['retrieval']['zenith_channels']
    ch_scan = inst_conf['retrieval']['scan_channels']
    
    # Validate channel configuration
    if not (len(ch_zenith) == len(ch_scan) == len(mwr_data.frequency)):
        raise MWRConfigError(
            f'Channel configuration mismatch: '
            f'zenith_channels={len(ch_zenith)}, scan_channels={len(ch_scan)}, '
            f'frequency dimension={len(mwr_data.frequency)}. All must be equal.'
        )
    
    # Configure surface data
    if has_surface_data:
        logger.info('Surface data from MWR measurements')
        sfc_data_type = constants.SFC_DATA_TYPE_MWR
        sfc_config = {
            'offset': 0,
            'rootname': 'mwr',
            'temp_error': constants.SFC_TEMP_ERROR_MWR,
            'rh_error': constants.SFC_RH_ERROR_MWR
        }
    else:
        logger.info('Surface data from model forecast')
        sfc_data_type = constants.SFC_DATA_TYPE_MODEL
        sfc_config = {
            'offset': met_sfc_offset,
            'rootname': 'met',
            'temp_error': constants.SFC_TEMP_ERROR_MODEL,
            'rh_error': constants.SFC_RH_ERROR_MODEL
        }
    
    # Build base configuration
    vip_config = {
        # Station information
        'station_lat': station_coords['latitude'],
        'station_lon': station_coords['longitude'],
        'station_alt': station_coords['altitude'],
        'station_psfc_max': constants.STATION_PSFC_MAX,
        'station_psfc_min': constants.STATION_PSFC_MIN,
        
        # MWR zenith configuration
        'mwr_n_tb_fields': len(mwr_data.frequency[ch_zenith]),
        'mwr_tb_freqs': mwr_data.frequency[ch_zenith].values,
        'mwr_tb_noise': inst_conf['retrieval']['tb_noise'][ch_zenith],
        'mwr_tb_bias': inst_conf['retrieval']['tb_bias'][ch_zenith],
        
        # Surface data configuration
        'ext_sfc_wv_type': sfc_data_type,
        'ext_sfc_temp_type': sfc_data_type,
        'ext_sfc_relative_height': sfc_config['offset'],
        'ext_sfc_rootname': sfc_config['rootname'],
        'ext_sfc_temp_random_error': sfc_config['temp_error'],
        'ext_sfc_rh_random_error': sfc_config['rh_error'],
        
        # File paths
        'mwr_path': tropoe_paths['mountpoint'],
        'mwr_rootname': tropoe_paths['mwr_basename'],
        'mwrscan_path': tropoe_paths['mountpoint'],
        'mwrscan_rootname': tropoe_paths['mwr_basename'],
        'mod_temp_prof_path': tropoe_paths['mountpoint'],
        'mod_wv_prof_path': tropoe_paths['mountpoint'],
        'cbh_path': tropoe_paths['mountpoint'],
        'ext_sfc_path': tropoe_paths['mountpoint'],
        
        # Output configuration
        'output_path': tropoe_paths['mountpoint'],
        'output_rootname': output_basename,
    }
    
    # Add scan configuration if available
    if any(ch_scan):
        logger.info('Configuring scan data for retrieval')
        scan_config = {
            'mwrscan_type': 4,
            'mwrscan_elev_field': 'ele',
            'mwrscan_freq_field': 'frequency',
            'mwrscan_tb_field_names': 'tb',
            'mwrscan_tb_field1_tbmax': 330.0,
            'mwrscan_time_delta': 0.1 / 60,
            'mwrscan_elevations': inst_conf['retrieval']['scan_ele'],
            'mwrscan_n_elevations': len(inst_conf['retrieval']['scan_ele']),
            'mwrscan_n_tb_fields': len(mwr_data.frequency[ch_scan]),
            'mwrscan_tb_freqs': mwr_data.frequency[ch_scan].values,
            'mwrscan_tb_noise': inst_conf['retrieval']['tb_noise'][ch_scan],
            'mwrscan_tb_bias': inst_conf['retrieval']['tb_bias'][ch_scan],
        }
        vip_config.update(scan_config)
    else:
        logger.info('No scan data for this retrieval')
    
    return vip_config, sfc_data_type


def write_vip_file(vip_base_config, vip_updates, output_filepath):
    """Write VIP configuration to file.
    
    Args:
        vip_base_config: Base VIP configuration dictionary
        vip_updates: Dictionary of updates to apply to base config
        output_filepath: Path where to write the VIP file
    """
    header = '# This file is automatically generated. Do not edit. To change settings modify retrieval config file.'
    vip_base_config.update(vip_updates)
    dict_to_file(
        vip_base_config,
        output_filepath,
        sep=' = ',
        header=header,
        remove_brackets=True,
        remove_parentheses=True,
        remove_braces=True
    )
    logger.debug(f'VIP configuration written to {output_filepath}')


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
    tropoe_run = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    logger.info('TROPoe run output:')
    logger.info(tropoe_run.stdout.decode('utf-8'))

def transform_units(data):
    """Transform all units of TROPoe output file to match units in E-PROFILE output files"""

    # unit_match contents. key: orig unit; value: (new unit, multiplier, adder)
    unit_match = {'C': ('K', 1, 273.15),
                  'km': ('m', 1e3, 0),
                  'g/kg': ('ppm', 1e3, 0),
                  'g/m2': ('kg m-2', 1e-3, 0),  # for liquid water path
                  'cm': ('kg m-2', 10, 0),  # for integrated water vapour
                  }
    unit_attribute = 'units'
    
    # Some exception where we should NOT apply any corrections:
    # TODO: check if exceptions can not be based on the "adder" values, essentially if adder is non zero we should not touch the sigma of this value
    exceptions = ['sigma_temperature']

    for var in data.variables:
        if hasattr(data[var], unit_attribute) and data[var].attrs[unit_attribute] in unit_match and var not in exceptions:
            transformer = unit_match[data[var].attrs[unit_attribute]]
            data[var] = data[var]*transformer[1] + transformer[2]
            data[var].attrs[unit_attribute] = transformer[0]
        

    return data

def height_to_altitude(data, station_altitude):
    """transform height above ground level to altitude above mean sea level and add as dataarray and coordinate

    Args:
        data: `xarray.Dataset` in which to change height to altitude
        station_altitude: single value or array defining station altitude (in an array the first entry is considered)

    Returns:
        updated dataset with altitude variable added (height also kept) and coordinate swapped from height to altitude
    """

    try:
        station_altitude = station_altitude[0]
    except TypeError:
        pass
    data.update({'station_altitude': station_altitude})
    data['altitude'] = data['height'] + data['station_altitude']
    return data.swap_dims({'height': 'altitude'})

def add_variables_attrs(data, derived_product_list):
    """Add variables attributes linked to the retrieval_type, retrieval_elevation_angles and retrieval_frequency"""
    
    # temperature
    data['temperature'].attrs['retrieval_type'] = 'optimal estimation'
    if data.attrs['VIP_mwrscan_type'] == '0': # Careful, if not specified, TROPoe output defaulf values for elevation angle and scan frequencies, even if none were used !
        data['temperature'].attrs['retrieval_elevation_angles'] = '90'
        data['temperature'].attrs['retrieval_frequency'] = data.attrs['VIP_mwr_tb_freqs']
        data['temperature'].attrs['retrieval_auxiliary_input'] = ''
        data['temperature'].attrs['retrieval_description'] = ''
    else:
        data['temperature'].attrs['retrieval_elevation_angles'] = '90, ' + data.attrs['VIP_mwrscan_elevations']
        data['temperature'].attrs['retrieval_frequency'] = data.attrs['VIP_mwr_tb_freqs']+data.attrs['VIP_mwrscan_tb_freqs']
        data['temperature'].attrs['retrieval_auxiliary_input'] = ''
        data['temperature'].attrs['retrieval_description'] = ''

    # water vapor
    data['waterVapor'].attrs['retrieval_type'] = 'optimal estimation'
    data['waterVapor'].attrs['retrieval_elevation_angles'] = '90'
    data['waterVapor'].attrs['retrieval_frequency'] = data.attrs['VIP_mwr_tb_freqs']
    data['waterVapor'].attrs['retrieval_auxiliary_input'] = ''
    data['waterVapor'].attrs['retrieval_description'] = ''

    # liquid water path
    data['lwp'].attrs['retrieval_type'] = 'optimal estimation'
    data['lwp'].attrs['retrieval_elevation_angles'] = '90'
    data['lwp'].attrs['retrieval_frequency'] = data.attrs['VIP_mwr_tb_freqs']
    data['lwp'].attrs['retrieval_auxiliary_input'] = ''
    data['lwp'].attrs['retrieval_description'] = ''

    for var in derived_product_list:
        data[var].attrs['retrieval_type'] = 'derived product'
        # data[var].attrs['retrieval_elevation_angles'] = ''
        # data[var].attrs['retrieval_frequency'] = ''

    return data

def extract_prior(data, tropoe_out_config):
    """
    Extracts prior information from the given data based on the TROPoe output configuration.
    #TODO: this function could be done more generic, e.g. by inputing a list of variables to extract prior information from.

    Args:
        data (xr.Dataset): The input data containing the variables to extract prior information from.
        tropoe_out_config (dict): The TROPoe output configuration dictionary.

    Returns:
        xr.Dataset: The input data with the prior information variables added.

    Raises:
        FileExistsError: If the tropoe_out_config argument is not a dictionary.
    """

    # read config file for TROPoe output
    if isinstance(tropoe_out_config, dict):
        tropoe_conf = tropoe_out_config
    else:
        raise FileExistsError("The argument 'conf' must be a conf dictionary")

    # Temperature
    data = data.assign(
        temperature_prior = xr.DataArray(
        data.Xa.where(data.arb1==tropoe_conf['temperature'], drop=True).values,
        coords= {'height':data.height},
        dims='height',
        attrs={'units':data.temperature.units},
        ),
    )
    
    # Water vapor
    data = data.assign(
        waterVapor_prior = xr.DataArray(
        data.Xa.where(data.arb1==tropoe_conf['waterVapor'], drop=True).data,
        coords= {'height':data.height},
        dims='height',
        attrs={'units':data.waterVapor.units},
        ),
    )
        
    # Liquid water path
    data = data.assign(
        lwp_prior = xr.DataArray(
        data.Xa.where(data.arb1==tropoe_conf['lwp'], drop=True).data,
        coords= {},
        attrs={'units':data.lwp.units},
        ),
    )
    return data

def add_flags(data):
    """
    Add dummy quality flags to the given data.
    TODO: define the quality flags.

    Parameters:
    data (xarray.Dataset): The input data.

    Returns:
    xarray.Dataset: The data with quality flags added.
    """
    
    # Temperature
    data['temperature_quality_flag'] = data.temperature.copy(data=0*data.temperature.data)
    # Water vapor
    data['waterVapor_quality_flag'] = data.waterVapor.copy(data=0*data.waterVapor.data)
    # Liquid water path
    data['lwp_quality_flag'] = data.lwp.copy(data=0*data.lwp.data)

    return data

def extract_avk(data, tropoe_out_config):
    """
    Extracts prior information from the given data based on the TROPoe output configuration.
    #TODO: this function could be done more generic, e.g. by inputing a list of variables to extract prior information from.

    Args:
        data (xr.Dataset): The input data containing the variables to extract prior information from.
        tropoe_out_config (dict): The TROPoe output configuration dictionary.

    Returns:
        xr.Dataset: The input data with the prior information variables added.

    Raises:
        FileExistsError: If the tropoe_out_config argument is not a dictionary.
    """

    # read config file for TROPoe output
    if isinstance(tropoe_out_config, dict):
        tropoe_conf = tropoe_out_config
    else:
        raise FileExistsError("The argument 'conf' must be a conf dictionary")
    
    data = data.assign(
        temperature_avk = xr.DataArray(
        data.Akernal_no_model[:,data.arb1==tropoe_conf['temperature'],data.arb2==tropoe_conf['temperature']].data,
        coords= {'time':data.time, 'altitude':data.altitude.data, 'avk_altitude':data.altitude.data},
        dims=['time','altitude','avk_altitude'],
        attrs={'long_name':'temperature averaging kernels'}
        ),
    )
    # Water vapor
    data = data.assign(
        waterVapor_avk = xr.DataArray(
        data.Akernal_no_model[:,data.arb1==tropoe_conf['waterVapor'],data.arb2==tropoe_conf['waterVapor']].data,
        coords= {'time':data.time, 'altitude':data.altitude.data, 'avk_altitude':data.altitude.data},
        dims=['time','altitude','avk_altitude'],
        attrs={'long_name':'water vapor averaging kernels'}
        ),
    )
    # Liquid water path
    data = data.assign(
        lwp_avk = xr.DataArray(
        data.Akernal_no_model[:,data.arb1==tropoe_conf['lwp'],data.arb2==tropoe_conf['lwp']].data.ravel(),
        coords= {'time':data.time},
        dims=['time'],
        attrs={'long_name':'liquid water path averaging kernels'}
        ),
    )
    return data

def extract_attrs(data):
    """
    Extracts some attributes from the TROPoe outputs and rename them.

    Args:
        data (xr.Dataset): The input data containing the variables to extract the attributes from.

    Returns:
        data (xr.Dataset): The input data with the added attributes

    """
    data.attrs['avg_instant'] = data.attrs['VIP_avg_instant']

    # zenith infos
    data.attrs['mwr_tb_freqs'] = data.attrs['VIP_mwr_tb_freqs']
    data.attrs['mwr_tb_bias'] = data.attrs['VIP_mwr_tb_bias']
    data.attrs['mwr_tb_noise'] = data.attrs['VIP_mwr_tb_noise']

    # scan infos
    data.attrs['mwrscan_elevations'] = data.attrs['VIP_mwrscan_elevations']
    data.attrs['mwrscan_tb_bias'] = data.attrs['VIP_mwrscan_tb_bias']
    data.attrs['mwrscan_tb_freqs'] = data.attrs['VIP_mwrscan_tb_freqs']
    data.attrs['mwrscan_tb_noise'] = data.attrs['VIP_mwrscan_tb_noise']

    # model infos
    data.attrs['mod_temp_prof_type'] = data.attrs['VIP_mod_temp_prof_type']
    data.attrs['mod_wv_prof_type'] = data.attrs['VIP_mod_wv_prof_type']

    return data

def extract_zenith_tbs(data, tropoe_out_config):
    # read config file for TROPoe output
    if isinstance(tropoe_out_config, dict):
        tropoe_conf = tropoe_out_config
    else:
        raise FileExistsError("The argument 'conf' must be a conf dictionary")
    
    # extract frequencies from attrs
    mwr_frequencies = [float(item) for item in data.attrs['VIP_mwr_tb_freqs'].split(', ')]

    # Measurement vector and FM:
    data = data.assign(
        Tb = xr.DataArray(
        data.obs_vector[:,data.obs_flag==tropoe_conf['zenithTb']].data,
        coords= {'time':data.time, 'frequency':mwr_frequencies},
        dims=['time','frequency'],
        attrs={'long_name':'zenith brightness temperature'}
        ),
    )
    data = data.assign(
        Tb_simulated = xr.DataArray(
        data.forward_calc[:,data.obs_flag==tropoe_conf['zenithTb']].data,
        coords= {'time':data.time, 'frequency':mwr_frequencies},
        dims=['time','frequency'],
        attrs={'long_name':'simulated brightness temperature'}
        ),
    )
    return data

if __name__ == '__main__':
    # run_tropoe('mwr_l12l2/data', 0, 'dummy/vip.txt', 'dummy/Xa_Sa.Lindenberg.55level.08.cdf')
    x = xr.open_dataset('~/Desktop/tropoe_out_0-20000-0-10393A.20230425.131005.nc')
    out = transform_units(x)
    pass
