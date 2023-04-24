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

if __name__ == '__main__':
    conf_inst = get_inst_config(abs_file_path('mwr_l12l2/config/config_0-20000-0-10393_A.yaml'))
    pass