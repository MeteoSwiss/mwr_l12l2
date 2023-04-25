import glob
import os

import datetime as dt
import numpy as np

from mwr_l12l2.utils.config_utils import get_inst_config, get_mars_config, merge_mars_inst_config
from mwr_l12l2.utils.file_uitls import abs_file_path


def write_mars_request(request_file, mars_conf, inst_conf_path, inst_conf_file_pattern='config_0*.yaml',
                       update_interval=6, availability_offset=6.5):
    """write request file for getting ECMWF model data using 'mars' for all stations that have a valid config file

    For dissemination time of ECMWF forecasts see https://confluence.ecmwf.int/display/DAC/Dissemination+schedule
    """

    format_request_date = '%Y-%m-%d'
    format_request_time = '%H:%M:%S'
    format_outfile_timestamp_date = '%Y%m%d'
    format_outfile_timestamp_time = '%H%M'

    if not isinstance(update_interval, int):
        raise TypeError("input argument 'update_interval' is expected to be an integer. "
                        'Update cycles at fractions of an hour are currently not supported')

    # get config files ready
    if not isinstance(mars_conf, dict):
        mars_conf = get_mars_config(abs_file_path(mars_conf))
    inst_conf_path = abs_file_path(inst_conf_path)
    inst_conf_files = glob.glob(os.path.join(inst_conf_path, inst_conf_file_pattern))

    # infer last available forecast run from current time
    time_act_avail = dt.datetime.now(tz=dt.timezone(dt.timedelta(0))) - dt.timedelta(hours=availability_offset)
    analysis_time_strs = {'date': time_act_avail.strftime(format_request_date),
                          'time': '{:02d}:00:00'.format((time_act_avail.hour//update_interval) * update_interval)}

    # initialise list of request file contents. It is a list of strings, one for each line.
    contents = ['# CARE: This file is automatically generated by {}. Do not edit.'.format(__file__),
                '',
                'retrieve,']

    # define part of request common to all stations (interpret None in time fields as most recent forecast)
    for key, val in mars_conf['request'].items():
        if key in analysis_time_strs and val is None:
            val = analysis_time_strs[key]
            mars_conf['request'][key] = val  # need to keep track of these modifications for timestamp of output file
        contents.append('  {}={},'.format(key, val))
    dt_date = dt.datetime.strptime(mars_conf['request']['date'], format_request_date)
    dt_time = dt.datetime.strptime(mars_conf['request']['time'], format_request_time)

    # define one request per stations (keys that are not re-set will be taken from previous request)
    for ind, inst_conf_file in enumerate(inst_conf_files):
        # prepare
        inst_conf = get_inst_config(inst_conf_file)
        conf = merge_mars_inst_config(mars_conf, inst_conf)
        lat_box = get_corner_coord(inst_conf['station_latitude'], conf['grid']['lat_offset'], conf['grid']['lat_res'])
        lon_box = get_corner_coord(inst_conf['station_longitude'], conf['grid']['lon_offset'], conf['grid']['lon_res'])
        outfile_path = abs_file_path(conf['outfile']['path'])
        outfile_stamp = '{}_{}_{}{}'.format(inst_conf['wigos_station_id'], inst_conf['instrument_id'],
                                            dt_date.strftime(format_outfile_timestamp_date),
                                            dt_date.strftime(format_outfile_timestamp_time))
        # append to request file contents
        if ind > 0:
            contents.append('retrieve,')
        contents.append('  grid={}/{},'.format(conf['grid']['lat_res'], conf['grid']['lon_res']))
        contents.append('  area={:.3f}/{:.3f}/{:.3f}/{:.3f},'.format(lat_box[1], lon_box[0], lat_box[0], lon_box[1]))
        contents.append('  target={}{}{}'.format(os.path.join(outfile_path, conf['outfile']['basename']),
                                                 outfile_stamp, conf['outfile']['extension']))
        contents.append('')

    with open(request_file, 'w') as f:
        f.write('\n'.join(contents))


def get_corner_coord(stn_coord, offset, resol):
    """get corners of a coordinate box around station coordinates which match model grid points"""
    stn_coord_rounded = round(stn_coord/resol) * resol  # round centre coordinate to model resolution
    return stn_coord_rounded + np.array(offset)


if __name__ == '__main__':
    write_mars_request('dummy_mars_request.txt', 'mwr_l12l2/config/mars_config.yaml', 'mwr_l12l2/config/')