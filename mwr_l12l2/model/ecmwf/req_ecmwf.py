import glob
import os

import datetime as dt
import numpy as np

from mwr_l12l2.utils.config_utils import get_inst_config, get_mars_config, merge_mars_inst_config
from mwr_l12l2.utils.file_utils import abs_file_path


def write_mars_request(request_file, mars_conf_fc, mars_conf_z, inst_conf_path, inst_conf_file_pattern='config_0*.yaml',
                       update_interval=6, availability_offset=6.5):
    """write request file for getting ECMWF model data using 'mars' for all stations that have a valid config file

    The function will use the current time to infer what is the expeceted issuing date of the last forecast.
    For dissemination time of ECMWF forecasts see https://confluence.ecmwf.int/display/DAC/Dissemination+schedule

    Args:
        request_file: file to be generated by this function to configure mars request
        mars_conf_fc: yaml config file (or dictionary) defining the request of forecast data
        mars_conf_z: yaml config file (or dictionary) defining the request of geopotential on lowest level from analysis
        inst_conf_path: directory where to look for instrument config files
        inst_conf_file_pattern (optional): filename pattern that inst config files match. Defaults to 'config_0*.yaml'
        update_interval (optional): interval of new forecasts becoming available in hours
        availability_offset (optional): delay after which a new forecast becomes available in hours
    """

    format_request_date = '%Y-%m-%d'
    format_request_time = '%H:%M:%S'
    format_outfile_timestamp_date = '%Y%m%d'
    format_outfile_timestamp_time = '%H%M'

    # check and get input ready
    request_file = abs_file_path(request_file)
    if not isinstance(mars_conf_fc, dict):
        mars_conf_fc = get_mars_config(abs_file_path(mars_conf_fc))
    if not isinstance(mars_conf_z, dict):
        mars_conf_z = get_mars_config(abs_file_path(mars_conf_z), mandatory_keys=['request', 'outfile'],
                                      mandatory_keys_request=['type', 'param', 'levelist', 'step'])
    inst_conf_path = abs_file_path(inst_conf_path)
    if not isinstance(update_interval, int):
        raise TypeError("input argument 'update_interval' is expected to be an integer. "
                        'Update cycles at fractions of an hour are currently not supported')

    # infer last available forecast run from current time
    time_now_utc = dt.datetime.now(tz=dt.timezone(dt.timedelta(0)))
    time_act_avail = time_now_utc - dt.timedelta(hours=availability_offset)
    analysis_time_strs = {'date': time_act_avail.strftime(format_request_date),
                          'time': '{:02d}:00:00'.format((time_act_avail.hour//update_interval) * update_interval)}

    # initialise list of request file contents. It is a list of strings, one for each line.
    request_header = '# This file was automatically generated by {} on {}. Do not edit.'.format(
        __file__, time_now_utc.strftime('%Y-%m-%d %H:%M:%S UTC'))
    contents_fc = [request_header, '', '', '# requesting forecast data:', '', 'retrieve,']
    contents_z = ['', '', '# requesting surface geopotential from analysis:', '', 'retrieve,']

    # define part of forecast request common to all stations (interpret None in time fields as most recent forecast)
    for key, val in mars_conf_fc['request'].items():
        if key in analysis_time_strs and val is None:
            val = analysis_time_strs[key]
            mars_conf_fc['request'][key] = val  # need to keep track of these modifications for timestamp of output file
        contents_fc.append('  {}={},'.format(key, val))
    dt_date = dt.datetime.strptime(mars_conf_fc['request']['date'], format_request_date)
    dt_time = dt.datetime.strptime(mars_conf_fc['request']['time'], format_request_time)

    # define part of analysis request common to all stations (no need for None interpretation)
    for key, val in mars_conf_z['request'].items():
        contents_z.append('  {}={},'.format(key, val))

    # define one request per stations (keys that are not re-set will be taken from previous request)
    inst_conf_files = glob.glob(os.path.join(inst_conf_path, inst_conf_file_pattern))
    for ind, inst_conf_file in enumerate(inst_conf_files):
        # merge instrument and mars configs. For mars, use fc as major config (grid, stn, time), z just for output here
        inst_conf = get_inst_config(inst_conf_file)
        conf = merge_mars_inst_config(mars_conf_fc, inst_conf)
        conf_z = merge_mars_inst_config(mars_conf_z, inst_conf)

        # prepare request
        lat_box = get_corner_coord(inst_conf['station_latitude'], conf['grid']['lat_offset'], conf['grid']['lat_res'])
        lon_box = get_corner_coord(inst_conf['station_longitude'], conf['grid']['lon_offset'], conf['grid']['lon_res'])
        area_str = '{:.3f}/{:.3f}/{:.3f}/{:.3f}'.format(lat_box[1], lon_box[0], lat_box[0], lon_box[1])
        grid_str = '{:.3f}/{:.3f}'.format(conf['grid']['lat_res'], conf['grid']['lon_res'])
        outfile_path = abs_file_path(conf['outfile']['path'])
        outfile_path_z = abs_file_path(conf_z['outfile']['path'])
        outfile_stamp_fc = '{}_{}_{}{}'.format(inst_conf['wigos_station_id'], inst_conf['instrument_id'],
                                            dt_date.strftime(format_outfile_timestamp_date),
                                            dt_time.strftime(format_outfile_timestamp_time))
        # different stamp for z excluding timestamp: simply re-use old files in case request for z is not yet terminated
        outfile_stamp_z = '{}_{}'.format(inst_conf['wigos_station_id'], inst_conf['instrument_id'])

        # append to forecast request file contents
        for cont in [contents_fc, contents_z]:
            if ind > 0:
                cont.append('retrieve,')
            cont.append('  grid={},'.format(grid_str))
            cont.append('  area={},'.format(area_str))
        contents_fc.append('  target={}{}{}'.format(os.path.join(outfile_path, conf['outfile']['basename']),
                                                    outfile_stamp_fc, conf['outfile']['extension']))
        contents_fc.append('')
        contents_z.append('  target={}{}{}'.format(os.path.join(outfile_path_z, conf_z['outfile']['basename']),
                                                   outfile_stamp_z, conf_z['outfile']['extension']))
        contents_z.append('')

    # concat everything and write request file
    contents = contents_fc + contents_z
    with open(request_file, 'w') as f:
        f.write('\n'.join(contents))


def get_corner_coord(stn_coord, offset, resol):
    """get corners of a coordinate box around station coordinates which match model grid points"""
    stn_coord_rounded = round(stn_coord/resol) * resol  # round centre coordinate to model resolution
    return stn_coord_rounded + np.array(offset)


if __name__ == '__main__':
    write_mars_request('mwr_l12l2/data/output/ecmwf/mars_request.txt',
                       'mwr_l12l2/config/mars_config_fc.yaml', 'mwr_l12l2/config/mars_config_z.yaml',
                       'mwr_l12l2/config/')