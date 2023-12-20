import os

import datetime as dt
import numpy as np

from pathlib import Path

import mwr_l12l2
from mwr_l12l2.errors import FilenameError, MWRInputError


def abs_file_path(*file_path):
    """
    Make a relative file_path absolute in respect to the mwr_l12l2 project directory.
    Absolute paths wil not be changed
    """
    path = Path(*file_path)
    if path.is_absolute():
        return path
    return Path(mwr_l12l2.__file__).parent.parent / path


def replace_path(path, part_to_replace, replace_by):
    """replace parts of a path with another path (e.g. useful when mounting a path to another location)"""
    rel_path = os.path.relpath(path, part_to_replace)
    return os.path.join(replace_by, rel_path)


def concat_filename(prefix, wigos, inst_id='', suffix='', ext='.nc'):
    """concatenate a filename according to E-PROFILE standards.

    Args:
        prefix: prefix of filename (including tailing _ if needed)
        wigos: WIGOS-ID (or any other ID) of the station
        inst_id: instrument ID. Will be appended to wigos using _ if not empty. Defaults to ''.
        suffix: suffix part after the station and instrument ids (incl. heading _ if needed). Defaults to ''.
        ext: extension. Defaults to '.nc'. Explicitly specify ext ='' for no extension
    """
    fn = prefix + wigos
    if inst_id:
        fn += '_'
        fn += inst_id
    fn += suffix
    fn += ext
    return fn


def datestr_from_filename(filename, suffix=''):
    """return date string from filename, assuming it to be the last date-like block (separated by _) before suffix + ext

    Accepted dates are in form 'yyyymmddHHMM', 'yyyymmddHHMMSS', 'yyyymmdd', 'yymm' etc. but not separated by -, _ or :

    Args:
        filename: filename as str. Can contain path and extension.
        suffix (optional): suffix of the filename coming after the date and before the extension. Defaults to '';
    Returns:
        string containing the date in same representation as in the filename
    """
    min_date_length = 4
    filename_cut = os.path.splitext(filename)[0]
    if len(suffix) > 0:
        filename_cut = filename_cut[0:-len(suffix)]  # zero length suffix would yield empty str, hence if-clause
    fn_parts = filename_cut.split('_')
    for block in reversed(fn_parts):  # try to find date str parts of filename, starting at the end
        if len(block) < min_date_length:
            continue
        if block.isdecimal():
            return block
        if block[1:].isdecimal() and len(block)-1 >= min_date_length:  # block has ID at start, e.g. _A202206010000
            return block[1:]
    if suffix:
        raise FilenameError("found no date in '{}' while ignoring suffix '{}'".format(filename, suffix))
    else:
        raise FilenameError("found no date in '{}'".format(filename))


def datetime64_from_filename(filename, *args, **kwargs):
    """get :class:`numpy.datetime64` object from filename. Calling as :func:`datestr_from_fielename`"""

    accepted_formats = {'yyyymmddHHMMSS': '%Y%m%d%H%M%S',  # matching between datestring formats and datetime format
                        'yyyymmddHHMM': '%Y%m%d%H%M',
                        'yyyymmddHH': '%Y%m%d%H',
                        'yyyymmdd': '%Y%m%d',
                        'yyyymm': '%Y%m'}  # only one entry per length of key as right one is picked by length

    dstr = datestr_from_filename(filename, *args, **kwargs)
    for dstr_format, datetime_format in accepted_formats.items():
        if len(dstr) == len(dstr_format):
            return np.datetime64(dt.datetime.strptime(dstr, datetime_format))
    raise FilenameError('length of date string in filename is {} what does not match any '
                        'of the accepted formats ({})'.format(len(dstr), accepted_formats))


def generate_output_filename(basename, timestamp_src, files_in=None, time=None, ext='nc'):
    """generate filename in form {basename}{timestamp}.{ext} where timestamp comes from input files or time vector

    Args:
        basename: the first part of the filename without the date
        timestamp_src: source of output file timestamp.
            Can be 'instamp_min'/'instamp_max' for using smallest/largest timestamp of input filenames (needs 'files_in)
            or 'time_min'/'time_max' for smallest/largest time in data in format yyyymmddHHMM (needs 'time').
        files_in: list of input filenames to processing as a basis for timestamp selection
        time: :class:`xarray.DataArray` time vector of the data in :class:`numpy.datetime64` format. Assume to be sorted
        ext (optional): filename extension. Defaults to 'nc'. Empty not permitted.
    """
    format_stamp = '%Y%m%d%H%M'  # only used for timestamp_src='time_min' or 'time_max'

    # handle input
    if timestamp_src in ['instamp_min', 'instamp_max']:
        if files_in is None:
            raise MWRInputError("if timestamp_src is 'instamp_min' or 'instamp_max' input 'files_in' must be given")
        timestamps = sorted([datestr_from_filename(f) for f in files_in], key=timestamp_to_float)
    elif timestamp_src in ['time_min', 'time_max']:
        if time is None:
            raise MWRInputError("if timestamp_src is 'time_min' or 'time_max' input 'time' must be given")

    # produce output timestamp
    if timestamp_src == 'instamp_min':
        timestamp = timestamps[0]
    elif timestamp_src == 'instamp_max':
        timestamp = timestamps[-1]
    elif timestamp_src == 'time_min':
        timestamp = time[0].dt.strftime(format_stamp).data
    elif timestamp_src == 'time_max':
        timestamp = time[-1].dt.strftime(format_stamp).data
    elif timestamp_src == 'time_mean':
        timestamp = np.mean(time).dt.strftime(format_stamp).data
    else:
        raise MWRInputError("Known values for 'timestamp_src' are {} but found '{}'".format(
            "['instamp_min', 'instamp_max', 'time_min', 'time_max']", timestamp_src))

    return '{}{}.{}'.format(basename, timestamp, ext)


def timestamp_to_float(timestamp):
    """transform timestamp string to a float between 0 and 1 (integer of timestamp normalised by its length)"""
    return int(timestamp)/10**len(timestamp)


def dict_to_file(data, file, sep, header=None, remove_brackets=False, remove_parentheses=False, remove_braces=False):
    """write dictionary contents to a file. One item per line matching keys and values using 'sep'.

    Args:
        data: dictionary to write to file in question. Numpy 1d-arrays as values are ok, matrices not
        file: output file incl. path and extension
        sep: separator sign between key and value as string. Can include whitespaces around separator.
        header: header string to write to the head of the file before the first dictionary item. Defaults to None
        remove_brackets (optional): Remove square brackets [ and ], e.g. from lists, while printing to file.
            Defaults to False
        remove_parentheses (optional): Remove parantheses ( and ), e.g. from tuples, while printing to file.
            Defaults to False
        remove_braces (optional): Remove curly braces { and } while printing to file. Defaults to False
    """

    with open(file, 'w') as f:
        if header is not None:
            f.write(header + '\n')
        for key, val in data.items():
            if isinstance(val, np.ndarray):  # ensure numpy arrays are printed with elements separated by commas
                val = list(val)
            val = str(val)
            if remove_brackets:
                val = val.replace('[', '').replace(']', '')
            if remove_parentheses:
                val = val.replace('(', '').replace(')', '')
            if remove_braces:
                val = val.replace('{', '').replace('}', '')
            f.write(sep.join([key, val]) + '\n')


if __name__ == '__main__':
    fn1 = concat_filename('L2_', '0-20000-0-06610')
    fn2 = concat_filename('L2_', '0-20000-0-06610', ext='.grb')
    fn3 = concat_filename('L2_', '0-20000-0-06610', 'A')
    fn4 = concat_filename('L2_', '0-20000-0-06610', 'A', '_testsuffix')
    fn5 = concat_filename('L2_', '0-20000-0-06610', suffix='*')
    fn6 = concat_filename('L2_', '0-20000-0-06610', suffix='*', ext='')

    dstr1 = datestr_from_filename('L2_0-20000-0-06610_A_20230828_20311201.nc', '20311201')  # 20230828
    dstr2 = datestr_from_filename('L2_0-20000-0-06610_A_20230828_20311201.nc')  # 20311201
    # the following shall raise: dstr3 = datestr_from_filename('L2_0-20000-0-06610_A.nc')

    dd = {'key1': 'val1', 'key2': 'val2'}
    dict_to_file(dd, 'test.vip', ' = ', '# this is just a test file')

    replace_path('tropoe/node_0/mwr/mwr.nc', 'tropoe/node_0', '/data')
    pass
