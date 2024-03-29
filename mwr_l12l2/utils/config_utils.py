import logging
import yaml

from mwr_l12l2.errors import MissingConfig, MWRConfigError
from mwr_l12l2.utils.data_utils import lists_to_np
from mwr_l12l2.utils.file_utils import abs_file_path


def get_conf(file):
    """get conf dictionary from yaml files. Don't do any checks on contents"""
    with open(file) as f:
        conf = yaml.load(f, Loader=yaml.FullLoader)
    return conf


def check_conf(conf, mandatory_keys, miss_description):
    """check for mandatory keys of conf dictionary

    if key is missing raises MissingConfig('xxx is a mandatory key ' + miss_description)
    """
    for key in mandatory_keys:
        if key not in conf:
            err_msg = ("'{}' is a mandatory key {}".format(key, miss_description))
            raise MissingConfig(err_msg)


def to_abspath(conf, keys):
    """transform paths corresponding to keys in conf dictionary to absolute paths and return conf dict"""
    for key in keys:
        conf[key] = abs_file_path(conf[key])
    return conf


def get_inst_config(file):
    """get configuration for each instrument and check for completeness of config file"""

    mandatory_keys = ['wigos_station_id', 'instrument_id', 'station_latitude', 'station_longitude', 'station_altitude',
                      # TODO: compare all of the previous keys with input in L1 nc or remove from config
                      'model_request', 'retrieval']
    # TODO: make reader get the following from L1 nc. give possibility to overwrite from config
    #         ncattrs = ['wigos_station_id', 'instrument_id', 'site_location', 'institution', 'principal_investigator',
    #                    'instrument_manufacturer', 'instrument_model', 'instrument_generation', 'instrument_hw_id',
    #                    'instrument_calibration_status', 'date_of_last_absolute_calibration',
    #                    'type_of_automatic_calibrations']
    mandatory_keys_model_request = ['grid']
    mandatory_keys_model_request_grid = ['lat_res', 'lon_res', 'lat_offset', 'lon_offset']
    mandatory_keys_retrieval = ['tb_noise', 'tb_bias', 'zenith_channels', 'scan_channels']

    conf = get_conf(file)

    # verify conf dictionary structure
    check_conf(conf, mandatory_keys, 'of instrument config files but is missing in {}'.format(file))
    check_conf(conf['model_request'], mandatory_keys_model_request,
               'of the model_request section in instrument config files but is missing in {}'.format(file))
    check_conf(conf['model_request']['grid'], mandatory_keys_model_request_grid,
               'of the model_request.grid section in instrument config files but is missing in {}'.format(file))
    check_conf(conf['retrieval'], mandatory_keys_retrieval,
               'of the retrieval section in instrument config files but is missing in {}'.format(file))

    # dimension checking for retrieval config
    if not (len(conf['retrieval']['tb_noise']) == len(conf['retrieval']['tb_bias'])
            == len(conf['retrieval']['zenith_channels']) == len(conf['retrieval']['scan_channels'])):
        raise MWRConfigError('Length of tb_noise ({}), tb_bias ({}), zenith_channels ({}) and scan_channels ({}) '
                             'does not match in {}'.format(len(conf['retrieval']['tb_noise']),
                                                           len(conf['retrieval']['tb_bias']),
                                                           len(conf['retrieval']['zenith_channels']),
                                                           len(conf['retrieval']['scan_channels']),
                                                           file))

    # transformation of lists to numpy arrays to allow logical indexing
    conf['retrieval'] = lists_to_np(conf['retrieval'])

    return conf


def get_retrieval_config(file):
    """get configuration for running the retrieval check for completeness of config file and ensure absolute paths"""
    mandatory_keys = ['data', 'vip']
    mandatory_keys_data = ['max_age',
                           'inst_config_dir', 'inst_config_file_prefix',
                           'mwr_dir', 'mwr_file_prefix', 'alc_dir', 'alc_file_prefix',
                           'model_dir', 'model_fc_file_prefix', 'model_fc_file_suffix', 'model_fc_file_ext',
                           'model_z_file_prefix', 'model_z_file_ext',
                           'tropoe_basedir', 'tropoe_subfolder_basename',
                           'vip_filename_tropoe', 'result_basefilename_tropoe',
                           'mwr_basefilename_tropoe', 'alc_basefilename_tropoe',
                           'model_prof_basefilename_tropoe', 'model_sfc_basefilename_tropoe']
    # define paths which shall be transformed to abs paths:
    paths_data = ['output_dir', 'inst_config_dir', 'mwr_dir', 'alc_dir', 'model_dir', 'tropoe_basedir']
    mandatory_keys_vip = []
    paths_vip = []  # paths that shall be transformed to abs paths

    conf = get_conf(file)

    check_conf(conf, mandatory_keys, 'of retrieval config files but is missing in {}.'.format(file))
    check_conf(conf['data'], mandatory_keys_data,
               "of field 'data' in retrieval config files but is missing in {}.".format(file))
    check_conf(conf['vip'], mandatory_keys_vip,
               "of field 'vip' in retrieval config files but is missing in {}.".format(file))
    conf['data'] = to_abspath(conf['data'], paths_data)
    conf['vip'] = to_abspath(conf['vip'], paths_vip)

    return conf


def get_mars_config(file, mandatory_keys=None, mandatory_keys_request=None):
    """get configuration for mars request to obtain ECMWF data and check for completeness of config file

    Args:
        file: configuration file in yaml format to read in
        mandatory_keys (optional): mandatory primary keys. Default is ['request', 'grid', 'outfile'] for full request.
            This list can be reduced for subsequent requests inheriting from the primary one
        mandatory_keys_request (optional): mandatory keys in request section. Default is [class', 'expver', 'type',
            'stream', 'levtype', 'levelist', 'param', 'date', 'time', 'step']. This list can be reduced for subsequent
            requests inheriting from the primary one
    """

    if mandatory_keys is None:
        mandatory_keys = ['request', 'grid', 'outfile']
    if mandatory_keys_request is None:
        mandatory_keys_request = ['class', 'expver', 'type', 'stream', 'levtype', 'levelist', 'param',
                                  'date', 'time', 'step']
    mandatory_keys_grid = ['lat_res', 'lon_res' , 'lat_offset', 'lon_offset']
    mandatory_keys_outfile = ['path', 'basename']

    conf = get_conf(file)

    # verify conf dictionary structure
    note_msg = "Note that some fields can be set to 'null' if waiting for input by instrument config or current time."
    check_conf(conf, mandatory_keys, ['of mars config files but is missing in {}. {}'.format(file, note_msg)])
    if 'request' in conf:
        check_conf(conf['request'], mandatory_keys_request,
                   "of field 'request' in mars config files but is missing in {}. {}".format(file, note_msg))
    if 'grid' in conf:
        check_conf(conf['grid'], mandatory_keys_grid,
                   "of field 'grid' in mars config files but is missing in {}. {}".format(file, note_msg))
    if 'outfile' in conf:
        check_conf(conf['outfile'], mandatory_keys_outfile,
                   "of field 'outfile' in mars config files but is missing in {}. {}".format(file, note_msg))

    return conf


def merge_mars_inst_config(mars_conf, inst_conf):
    """merge mars config and definitions in instrument config for model request giving instrument config precedence"""

    inst_conf_mars_block = 'model_request'

    merged_conf = mars_conf
    if inst_conf_mars_block in inst_conf:
        for block_key in inst_conf[inst_conf_mars_block]:
            if block_key not in merged_conf:
                continue  # only fill primary keys which are also in mars request. Enforce presence by read-in check.
            for key, val in inst_conf[inst_conf_mars_block][block_key].items():
                merged_conf[block_key][key] = val

    return merged_conf


def get_nc_format_config(file):
    """get configuration for output NetCDF format and check for completeness of config file"""

    mandatory_keys = ['dimensions', 'variables', 'attributes']
    mandatory_variable_keys = ['name', 'dim', 'type', '_FillValue', 'optional', 'attributes']
    mandatory_dimension_keys = ['unlimited', 'fixed']

    conf = get_conf(file)

    # verify conf dictionary structure
    check_conf(conf, mandatory_keys,
               'of config files defining output NetCDF format but is missing in {}'.format(file))
    check_conf(conf['dimensions'], mandatory_dimension_keys,
               "of 'dimensions' config files defining output NetCDF format but is missing in {}".format(file))
    for varname, varval in conf['variables'].items():
        check_conf(varval, mandatory_variable_keys,
                   "of each variable in config files defining output NetCDF format but is missing for '{}' in {}"
                   .format(varname, file))
        if not isinstance(varval['dim'], list):
            raise MWRConfigError("The value attributed to 'dim' in variable '{}' is not a list in {}"
                                 .format(varname, file))

    return conf


def get_log_config(file):
    """get configuration for logger and check for completeness of config file"""

    mandatory_keys = ['logger_name', 'loglevel_stdout', 'write_logfile']
    mandatory_keys_file = ['logfile_path', 'logfile_basename', 'logfile_ext', 'logfile_timestamp_format',
                           'loglevel_file']

    conf = get_conf(file)
    check_conf(conf, mandatory_keys,
               'of logs config files but is missing in {}'.format(file))
    if conf['write_logfile']:
        check_conf(conf, mandatory_keys_file,
                   "of logs config files if 'write_logfile' is True, but is missing in {}".format(file))

    conf = interpret_loglevel(conf)

    return conf


def interpret_loglevel(conf):
    """helper function to replace logs level strings in logs level of logging library"""

    pattern = 'loglevel'

    level_keys = [s for s in conf.keys() if pattern in s]
    for level_key in level_keys:
        conf[level_key] = getattr(logging, conf[level_key].upper(), None)
        if not isinstance(conf[level_key], int):
            raise MWRConfigError("value of '{}' in logs config does not correspond to any known logs level of logging"
                                 .format(level_key))

    return conf


if __name__ == '__main__':
    conf_inst = get_inst_config(abs_file_path('mwr_l12l2/config/config_0-20000-0-10393_A.yaml'))
    conf_ret = get_retrieval_config(abs_file_path('mwr_l12l2/config/retrieval_config.yaml'))
    conf_mars = get_mars_config(abs_file_path('mwr_l12l2/config/mars_config_fc.yaml'))
    pass
