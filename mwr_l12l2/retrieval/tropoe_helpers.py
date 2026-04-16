import os.path
import subprocess
import uuid

import numpy as np
import xarray as xr

from mwr_l12l2.utils.data_utils import scalars_to_time, vectors_to_time, set_encoding, setbit
from mwr_l12l2.utils.file_utils import abs_file_path, replace_path
from mwr_l12l2.log import logger
from mwr_l12l2.errors import MWRConfigError
from mwr_l12l2.utils.file_utils import dict_to_file

class TROPoeRetrievalConstants:
    """
    Class containing code and constants used in VIP file to define retrievals.
    These should not change except if TROPoe itself changes and therefore should not be part of the config file.
    """
    MWR_SCAN_TYPE = 4  # MWR scan data type code
    
    # Surface data type codes for TROPoe VIP file (0 is missing, >1 is either model or MWR)
    SFC_DATA_TYPE_MISSING = 0
    SFC_DATA_TYPE_PROVIDED = 1
    
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
                    met_sfc_offset, tropoe_paths, output_basename, retrieval_conf):
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
        vip_conf: VIP configuration dictionary from retrieval config
        
    Returns:
        dict: VIP configuration parameters ready for writing
        int: Surface data type code (for setting ext_sfc_data_type)
        
    Raises:
        MWRConfigError: If channel configuration is invalid
    """
    vip_conf = retrieval_conf['vip']
    ch_zenith = inst_conf['retrieval']['zenith_channels']
    ch_scan = inst_conf['retrieval']['scan_channels']
    
    # Validate channel configuration
    if not (len(ch_zenith) == len(ch_scan) == len(mwr_data.frequency)):
        raise MWRConfigError(
            f'Channel configuration mismatch: '
            f'zenith_channels={len(ch_zenith)}, scan_channels={len(ch_scan)}, '
            f'frequency dimension={len(mwr_data.frequency)}. All must be equal.'
        )
  
    # Build configuration updates to merge with base vip_conf
    vip_updates = {
        'tres': retrieval_conf['general']['retrieval_time'],  # retrieval time in minutes
        
        # Station information
        'station_lat': station_coords['latitude'],
        'station_lon': station_coords['longitude'],
        'station_alt': station_coords['altitude'],
        'station_pres': station_coords['pressure'],
        'station_psfc_min': station_coords['station_psfc_min'],
        'station_psfc_max': station_coords['station_psfc_max'],

        # MWR zenith configuration
        'mwr_n_tb_fields': len(mwr_data.frequency[ch_zenith]),
        'mwr_tb_freqs': mwr_data.frequency[ch_zenith].values,
        'mwr_tb_noise': inst_conf['retrieval']['tb_noise'][ch_zenith],
        'mwr_tb_bias': inst_conf['retrieval']['tb_bias'][ch_zenith],
        
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
    
    # Add scan configuration if available #TODO: check that specified scan channels are actually present in the data and handle case where they are not (e.g. if scan data is missing for this instrument)
    if (any(ch_scan)) & (len(inst_conf['retrieval']['scan_ele'])>0):
        logger.info('Configuring scan data for retrieval')
        scan_config = {
            'mwrscan_type': TROPoeRetrievalConstants.MWR_SCAN_TYPE,
            'mwrscan_elev_field': 'ele',
            'mwrscan_freq_field': 'frequency',
            'mwrscan_tb_field_names': 'tb',
            'mwrscan_tb_field1_tbmax': 330.0,
            #'mwrscan_time_delta': 0.1 / 60,
            'mwrscan_elevations': inst_conf['retrieval']['scan_ele'],
            'mwrscan_n_elevations': len(inst_conf['retrieval']['scan_ele']),
            'mwrscan_n_tb_fields': len(mwr_data.frequency[ch_scan]),
            'mwrscan_tb_freqs': mwr_data.frequency[ch_scan].values,
            'mwrscan_tb_noise': inst_conf['retrieval']['tb_noise'][ch_scan],
            'mwrscan_tb_bias': inst_conf['retrieval']['tb_bias'][ch_scan],
        }
        vip_updates.update(scan_config)
    else:
        logger.warning('No scan data for this retrieval')
        #TODO: ensure TROPoe handles this correctly when no scan data is provided, seems that it might be using some default RDX values...
    
    # Merge updates into base vip configuration
    vip_conf.update(vip_updates)
    
    # Updates related to surface meteorological data (only if available)  
    if has_surface_data:
        logger.info('Surface data are complete and will be read from MWR met station')
        sfc_data_type = TROPoeRetrievalConstants.SFC_DATA_TYPE_PROVIDED
    else:
        logger.warning('No or incomplete surface met data found')
        logger.warning('For now, we are not implementing partial surface data from model, all or nothing')
        sfc_data_type = TROPoeRetrievalConstants.SFC_DATA_TYPE_MISSING
        # # TODO: define this from model data
        # # sfc_pressure = 980.0  # hPa - default value
        # # sfc_temp_error_model = 1.0  # K - temperature error for surface model data
        # # sfc_rh_error_model = 6.0  # % - relative humidity error for surface model data
        
        vip_updates_sfc_data = {
        #     #'station_pres': sfc_pressure,
            'ext_sfc_wv_type': sfc_data_type, # specify that sfc data are missing
            'ext_sfc_temp_type': sfc_data_type, # specify that sfc data are missing
        #     # 'ext_sfc_relative_height': met_sfc_offset,
        #     # 'ext_sfc_rootname': 'met',
        #     # 'ext_sfc_temp_random_error': sfc_temp_error_model,
        #     # 'ext_sfc_rh_random_error': sfc_rh_error_model,
        #     # 'ext_sfc_pres_type': 0,
        #     # 'ext_sfc_time_format': -1,
        #     # 'ext_sfc_pres_fieldname': 'air_pressure',
        #     # 'ext_sfc_pres_units': 2,
        #     # 'ext_sfc_temp_fieldname': 'air_temperature',
        #     # 'ext_sfc_temp_units': 2 # Kelvin
        }
        
        # Merge surface data updates    
        vip_conf.update(vip_updates_sfc_data)
    
    return vip_conf, sfc_data_type

def write_vip_file(vip_config, output_filepath):
    """Write VIP configuration to file.
    
    Args:
        vip_config: Complete VIP configuration dictionary (already merged)
        output_filepath: Path where to write the VIP file
    """
    header = '# This file is automatically generated. Do not edit. To change settings modify retrieval config file.'
    
    dict_to_file(
        vip_config,
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
               verbosity=1, memory_limit='4g', cpu_limit=None, container_name=None, timeout=3600):
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
        memory_limit (optional): memory limit for container (e.g., '4g', '2g'). Defaults to '4g'.
            Set to None to disable memory limiting.
        cpu_limit (optional): CPU limit for container (e.g., '1.0' for 1 CPU). Defaults to None (no limit).
        container_name (optional): unique name for the container. Auto-generated if None.
        timeout (optional): timeout in seconds for the container execution. Defaults to 3600 (1 hour).
            Set to None to disable timeout.
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

    # Generate unique container name for logging purposes
    if container_name is None:
        container_name = f'tropoe_{date_str}_{uuid.uuid4().hex[:8]}'

    # Create unique tmp directory using absolute path
    # Use os.path.abspath to ensure we get a proper absolute path string
    abs_tmp_path = os.path.abspath(str(abs_file_path(tmp_path)))
    unique_tmp = os.path.join(abs_tmp_path, container_name)
    os.makedirs(unique_tmp, exist_ok=True)

    # Get absolute path for data_path as well
    abs_data_path = os.path.abspath(str(abs_file_path(data_path)))

    # construct cmd for subprocess
    # Note: We don't use --name to avoid conflicts when containers fail to clean up
    cmd = ['podman', 'run', '-u', 'root', '--rm',
           '--pids-limit', '-1',  # disable PID limit to avoid issues with parallel processes inside container
           '--ulimit', 'nofile=65535:65535',  # increase open file limit to prevent "Too many open files" errors
           '-v', '{}:{}'.format(abs_data_path, data_mountpoint),
           '-v', '{}:/tmp2'.format(unique_tmp),
           '-e', 'app=TROPoe',
           '-e', 'yyyymmdd=' + date_str,
           '-e', 'shour={}'.format(start_hour),
           '-e', 'ehour={}'.format(end_hour),
           '-e', 'vfile=' + vip_fullpath,  # path inside container, e.g. relative to dir mapped to /data
           '-e', 'pfile=' + apriori_fullpath,  # path inside container, e.g. relative to dir mapped to /data
           '-e', 'verbose={}'.format(verbosity)]
    
    # Add resource limits if specified
    if memory_limit:
        cmd.extend(['--memory', memory_limit])
    if cpu_limit:
        cmd.extend(['--cpus', str(cpu_limit)])
    
    cmd.append(tropoe_img)
    logger.debug('Running TROPoe command: %s', ' '.join(cmd))
    
    try:
        tropoe_run = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error('TROPoe container %s timed out after %d seconds', container_name, timeout)
        return

    stdout_lines = tropoe_run.stdout.decode('utf-8', errors='replace').splitlines()
    if stdout_lines:
        logger.debug('--- TROPoe stdout ---')
        for line in stdout_lines:
            logger.debug('[TROPoe] %s', line)

    stderr_lines = tropoe_run.stderr.decode('utf-8', errors='replace').splitlines()
    if stderr_lines:
        logger.warning('--- TROPoe stderr ---')
        for line in stderr_lines:
            logger.warning('[TROPoe stderr] %s', line)

    if tropoe_run.returncode != 0:
        logger.error('TROPoe exited with non-zero return code %d', tropoe_run.returncode)

def transform_units(data):
    """Transform all units of TROPoe output file to match units in E-PROFILE output files"""

    # unit_match contents. key: orig unit; value: (new unit, multiplier, adder)
    unit_match = {'C': ('K', 1, 273.15),
                  'km': ('m', 1e3, 0),
                  'g/kg': ('kg/kg', 1e-3, 0),
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

def add_retrieved_variables_attrs(data):
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

    return data

def extract_prior(data, tropoe_conf):
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

def add_quality_flags(data, operational, mwr_quality_checked, cdfs_thresholds_dict):
    """
    Convert TROPoe integer quality flags to bitwise encoding and add retrieved specific variable flags
    
    TROPoe qc_flag values:
    - 0: Good quality (retrieval OK)
    - 2: Retrieval did not converge
    - 3: Retrieval converged but RMS between observed_vector and forward_calc is too large
    - 4: Gamma value of the retrieval was too large
    
    Bitwise mapping:
    - 0 (no bits set): Good quality (qc_flag == 0)
    - bit 0: Careful, MWR L1 checked not performed (qc_flag == 1)
    - bit 1: Non-convergence (qc_flag == 2)
    - bit 2: High RMS (qc_flag == 3)
    - bit 3: High gamma (qc_flag == 4)

    Parameters:
    data (xarray.Dataset): The input data with qc_flag variable.
    mwr_quality_checked (bool): Flag indicating whether MWR quality checks have been performed.
    cdfs_thresholds_dict (dict): Dictionary containing the thresholds for the cumulative distribution functions (CDFs) of temperature and water vapor.

    Returns:
    xarray.Dataset: The data with bitwise quality flags added.
    """
    # Initialize quality_flag with zeros (all good by default)
    quality_flag = data.qc_flag.copy(data=np.zeros_like(data.qc_flag.data, dtype=int))
    
    # Convert TROPoe integer flags to bitwise encoding
    # bit 0: when no checks have been performed on MWR L1 data
    if not mwr_quality_checked and operational:  # we only set this bit if we are in operational mode, otherwise for research mode we want to keep all data even if MWR quality checks have not been performed (e.g. for testing purposes)
        quality_flag = setbit(quality_flag, 0)
    
    # bit 1: Non-convergence (value 2)
    quality_flag = xr.where(data.qc_flag == 2, setbit(quality_flag, 1), quality_flag)
    # bit 2: High RMS (value 3)
    quality_flag = xr.where(data.qc_flag == 3, setbit(quality_flag, 2), quality_flag)
    # bit 3: High gamma (value 4)
    quality_flag = xr.where(data.qc_flag == 4, setbit(quality_flag, 3), quality_flag)
    
    rmsa_threshold = data.qc_flag.attrs.get('RMSa_threshold_used_for_QC', None)
    gamma_threshold = data.qc_flag.attrs.get('gamma_threshold_used_for_QC', None)
    
    data['quality_flag'] = quality_flag
    data['quality_flag'].attrs['thresholds'] = 'Thresholds used for quality control: RMSa = {}, gamma = {}'.format(rmsa_threshold, gamma_threshold)

    # Variable-specific quality flags (initialized to either 0 or 1 depending on quality_flag and extended in dims, can be populated based on specific criteria)
    profile_qc = xr.where(quality_flag.expand_dims({'altitude': data.altitude}, axis=1).transpose('time', 'altitude')==0, 0, 1)  # bit 0 for generic suspect quality, we set all altitudes to bad quality if the profile is flagged as suspect, otherwise good quality by default (can be further refined based on specific criteria, e.g. cdf thresholds)

    # variable-specific qc
    data['temperature_quality_flag'] = profile_qc.copy()
    data['waterVapor_quality_flag'] = profile_qc.copy()
    
    # Use the the cdfs of temperature and water vapor retrievals to set upper limits of good quality flags.
    # find the altitude where cdfs_temperature and cdfs_waterVapor are above the thresholds defined in the config file and set the corresponding bits in the quality flags for all altitudes above this limit.
    if 'cdfs_temperature_no_model' in data and 'cdfs_waterVapor_no_model' in data and \
        'temperature_cdf_threshold' in cdfs_thresholds_dict and 'waterVapor_cdf_threshold' in cdfs_thresholds_dict:
        temp_threshold = cdfs_thresholds_dict['temperature_cdf_threshold']*data.cdfs_temperature.max(dim='altitude') # we multiply the threshold by the max cdf value to get the actual threshold value for this profile, as the cdf values can be between 0 and 1 and the threshold in the config file is defined as a fraction of the max cdf value (e.g. 0.5 means that we want to flag all altitudes where cdf is above 50% of its max value)
        wv_threshold = cdfs_thresholds_dict['waterVapor_cdf_threshold']*data.cdfs_waterVapor.max(dim='altitude')
        
        temp_max_altitudes = np.nanmax(data.where(data.cdfs_temperature < temp_threshold, drop=True).altitude.data)
        wv_max_altitudes = np.nanmax(data.where(data.cdfs_waterVapor < wv_threshold, drop=True).altitude.data)

        # Set the bits for altitudes above the good altitude limits to "bad quality" (value == 1)
        data['temperature_quality_flag'] = data['temperature_quality_flag'].where(data.altitude < temp_max_altitudes, 1) # 1 for temperature cdf threshold
        data['waterVapor_quality_flag'] = data['waterVapor_quality_flag'].where(data.altitude < wv_max_altitudes, 1) # 1 for water vapor cdf threshold
        # Add comments on how the flags were set based on the cdf thresholds
        data['temperature_quality_flag'].attrs['comment'] = 'Temperature quality flag set to 0 (good quality) for altitudes where the cdf of temperature retrievals is below the threshold of {}% of the max cdf value, and 1 (bad quality) for altitudes above this limit.'.format(cdfs_thresholds_dict['temperature_cdf_threshold']*100)
        data['waterVapor_quality_flag'].attrs['comment'] = 'Water vapor quality flag set to 0 (good quality) for altitudes where the cdf of water vapor retrievals is below the threshold of {}% of the max cdf value, and 1 (bad quality) for altitudes above this limit.'.format(cdfs_thresholds_dict['waterVapor_cdf_threshold']*100)
        
    # Liquid water path
    data['lwp_quality_flag'] = xr.where(quality_flag==0, 0, 1)  # 0 for generic suspect quality, we set lwp to bad quality if the profile is flagged as suspect, otherwise good quality by default (can be further refined based on specific criteria, e.g. cdf thresholds)

    return data

def set_observation_flag(data, tropoe_conf):
    '''
    Set the observing_geometry_flag in data based on the presence of scan data in the TROPoe output. If scan data is present, we set the flag to 0 (scanning), otherwise to 1 (single-pointing). 

    In TROPoe, the scanning angles used in the retrieval at each time step is encoded in the obs_vector variable.
    '''
    # Initiate the observing_geometry_flag variable with 1 (= single_pointing) by default, we will set it to 0 for time steps where scan data is present
    data['observing_geometry_flag'] = xr.DataArray(
        data=np.ones_like(data.time.data, dtype=int),
        coords={'time': data.time},
        dims=['time'],
    )
    
    scan_data = data.obs_vector[:,data.obs_flag==tropoe_conf['scanTb']].data

    if scan_data.size > 1:
        scan_tb_tropoe = xr.DataArray(
            data.obs_vector[:,data.obs_flag==tropoe_conf['scanTb']].data,
            coords= {'time':data.time, 'scan_obs':data.obs_dimension[data.obs_flag==tropoe_conf['scanTb']].data},
            dims=['time','scan_obs'],
            attrs={'long_name':'scan brightness temperature observations'}
        )
        
        # set observing_geometry_flag to 1 for time steps where scan data is present (multiple-pointing), otherwise keep it at 0 (single-pointing)    
        data['observing_geometry_flag'] = xr.where(scan_tb_tropoe.scan_obs.data.size > 0, 0, data['observing_geometry_flag'])
        # encode angle used
        data['observing_geometry_flag'].attrs['comment'] = 'Observing geometry flag: 0 for multiple-pointing, 1 for single-pointing. Determined based on the presence of scan brightness temperature observations in the MWR observations and actually used in retrievals'
        # scan angles are ?= scan_tb_tropoe.scan_obs.data -> add value in data attrs as string to avoid issues with encoding when writing to netcdf (e.g. if we want to write the actual angles used in the retrieval, which can be different from the ones specified in the config file if some of them were not used by TROPoe for some reason, e.g. due to quality control)
        str_angles = ','.join([str(np.round(angle,5)) for angle in scan_tb_tropoe.scan_obs.data])
        data['observing_geometry_flag'].attrs['scan_angles_used_in_retrieval'] = str_angles
        # propagate attributes from tropoe obs_flag "value_10"
        data['observing_geometry_flag'].attrs['scan_angles_encoding_comment'] = data.obs_flag.attrs['value_10_comment1']
    
    return data
    
def extract_avk(data, tropoe_conf):
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

def add_lat_lon_vectors(data):
    # First rename the latitude and longitude variables to station_latitude and station_longitude
    data = data.rename({'lat': 'station_latitude', 'lon': 'station_longitude'})
    
    # add proper standard attributes to the station latitude and longitude variables
    data['station_latitude'].attrs.update({'standard_name': 'deployment_latitude'})
    data['station_longitude'].attrs.update({'standard_name': 'deployment_longitude'})
    # Add the latitude and longitude variables as 2D vector (with same value repeated in all altitudes)
    data = data.assign(
        latitude = xr.DataArray(
        data=np.repeat(data.station_latitude.values[:, np.newaxis], data.sizes['altitude'], axis=1),
        coords= {'time':data.time, 'altitude':data.altitude.data},
        dims=['time','altitude'],
        attrs={'standard_name':'latitude',
               'long_name':'Latitude for each measurement',
               'units':'degrees_north',
            }
        ),
    )
    data = data.assign(
        longitude = xr.DataArray(
        data=np.repeat(data.station_longitude.values[:, np.newaxis], data.sizes['altitude'], axis=1),
        coords= {'time':data.time, 'altitude':data.altitude.data},
        dims=['time','altitude'],
        attrs={'standard_name':'longitude',
               'long_name':'Longitude for each measurement',
               'units':'degrees_east',
            }
        ),
    )
    return data
    
def convert_tropoe_output(retrieval_conf, tropoe_data, mwr_l1_data, tropoe_out_config, 
                               use_model_data=False, ext_sfc_data_type=None):
    """
    Convert TROPoe output data into E-Profile L2 format.

    This function transforms raw TROPoe output into the standardized E-Profile format by:
    - Extracting prior information and averaging kernels
    - Converting units to match E-Profile standards
    - Converting height above ground level to altitude above mean sea level and cut to max altitude
    - Propagating Level 1 metadata
    - Adding quality flags and variable attributes
    - Setting retrieval type and surface data information
    
    Args:
        conf: Configuration dictionary for the retrieval (not used in current implementation but can be useful for future extensions)
        tropoe_data: xarray Dataset from TROPoe output
        mwr_l1_data: xarray Dataset from Level 1 MWR data
        tropoe_out_config: TROPoe output configuration dict
        use_model_data: Whether model data was used in retrieval (default: False)
        ext_sfc_data_type: Surface data type constant (default: None)
        
    Returns:
        xarray Dataset ready for E-Profile output
    """
    # read config file for TROPoe output
    if isinstance(tropoe_out_config, dict):
        tropoe_conf = tropoe_out_config
    else:
        raise FileExistsError("The argument 'conf' must be a conf dictionary")
    
    # Extract prior information
    data = extract_prior(tropoe_data, tropoe_conf)
    
    # Propagate some L1 variable
    data['azi'] = np.median(mwr_l1_data.azi.values)
    data['quality_flag_status'] = mwr_l1_data.quality_flag_status.isel(time=0, frequency=0).values
    
    # Set the observing geometry flag based on the presence of scan data in the TROPoe output (0 for scanning, 1 for single-pointing)
    data = set_observation_flag(data, tropoe_conf)
    
    # Transform units to E-PROFILE standards
    data = transform_units(data)
            
    # Convert height to altitude
    data = height_to_altitude(data, mwr_l1_data.station_altitude)
    data = scalars_to_time(data, ['lat', 'lon', 'azi', 'station_altitude', 'lwp_prior'])
    data = vectors_to_time(data, ['temperature_prior', 'waterVapor_prior', 'quality_flag_status'])
    
    # Add the latitude and longitude variables as 2D vector
    # TODO: remove the if condition once L2 data format is agreed
    if retrieval_conf['general']['operational']:
        data = add_lat_lon_vectors(data)
    
    # Extract averaging kernels
    data = extract_avk(data, tropoe_out_config)
    
    # Add quality flags       
    data = add_quality_flags(
        data, 
        operational=retrieval_conf['general']['operational'], 
        mwr_quality_checked=retrieval_conf['data']['check_mwr_quality'], 
        cdfs_thresholds_dict={
            'temperature_cdf_threshold': retrieval_conf['data']['temperature_cdf_threshold'],
            'waterVapor_cdf_threshold': retrieval_conf['data']['waterVapor_cdf_threshold'],
        }
    )
    
    # Add variable attributes for retrieved products
    data = add_retrieved_variables_attrs(data)
    
    # Propagate L1 global attributes
    for attr in mwr_l1_data.attrs:
        data.attrs[attr] = mwr_l1_data.attrs[attr]
    
    # Extract and clean TROPoe attributes
    data = extract_attrs(data)
    
    # Add retrieval type
    data.attrs['retrieval_type'] = '1DVAR' if use_model_data else 'optimal estimation'
    
    # Add surface data type info
    # if ext_sfc_data_type == TROPoeRetrievalConstants.SFC_DATA_TYPE_MODEL:
    #     data.attrs['ext_sfc_temp_type'] = 'model'
    #     data.attrs['ext_sfc_wv_type'] = 'model'
    if ext_sfc_data_type == TROPoeRetrievalConstants.SFC_DATA_TYPE_PROVIDED:
        data.attrs['ext_sfc_temp_type'] = 'mwr'
        data.attrs['ext_sfc_wv_type'] = 'mwr'
    else:
        data.attrs['ext_sfc_temp_type'] = 'unknown'
        data.attrs['ext_sfc_wv_type'] = 'unknown'
    
    # Remove VIP attributes
    for attr in list(data.attrs):
        if 'VIP' in attr:
            del data.attrs[attr]
    
    return data
