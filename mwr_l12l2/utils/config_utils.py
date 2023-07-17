import yaml

from mwr_l12l2.errors import MissingConfig
from mwr_l12l2.utils.file_uitls import abs_file_path


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

    mandatory_keys = ['wigos_station_id', 'instrument_id', 'station_latitude', 'station_longitude', 'station_altitude']
    # TODO: compare all of the previous keys wiht input in L1 nc
    optional_keys = ['input_directory', 'output_directory', 'base_filename_in', 'base_filename_out', 'nc_attributes']

    # TODO: make reader get the following from L1 nc. give possibility to overwrite from config
    #         ncattrs = ['wigos_station_id', 'instrument_id', 'site_location', 'institution', 'principal_investigator',
    #                    'instrument_manufacturer', 'instrument_model', 'instrument_generation', 'instrument_hw_id',
    #                    'instrument_calibration_status', 'date_of_last_absolute_calibration',
    #                    'type_of_automatic_calibrations']

    conf = get_conf(file)

    # verify conf dictionary structure
    check_conf(conf, mandatory_keys, 'of instrument config files but is missing in {}'.format(file))

    return conf

def get_retrieval_config(file):
    """get configuration for running the retrieval check for completeness of config file and ensure absolute paths"""
    mandatory_keys = ['data', 'vip']
    mandatory_keys_data = ['max_age',
                           'mwr_dir', 'mwr_file_prefix', 'alc_dir', 'alc_file_prefix',
                           'model_dir', 'model_fc_file_prefix', 'model_fc_nc_file_suffix', 'model_z_file_prefix',
                           'tropoe_basedir', 'tropoe_subfolder_basename', 'mwr_filename_tropoe', 'alc_filename_tropoe',
                           'model_prof_filename_tropoe', 'model_sfc_filename_tropoe']
    paths_data = ['mwr_dir', 'alc_dir', 'model_dir', 'tropoe_basedir']  # paths that shall be transformed to abs paths
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


if __name__ == '__main__':
    conf_inst = get_inst_config(abs_file_path('mwr_l12l2/config/config_0-20000-0-10393_A.yaml'))
    conf_ret = get_retrieval_config(abs_file_path('mwr_l12l2/config/retrieval_config.yaml'))
    conf_mars = get_mars_config(abs_file_path('mwr_l12l2/config/mars_config_fc.yaml'))
    pass