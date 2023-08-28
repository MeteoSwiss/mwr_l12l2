import os

from pathlib import Path

import mwr_l12l2
from mwr_l12l2.errors import FilenameError


def abs_file_path(*file_path):
    """
    Make a relative file_path absolute in respect to the mwr_raw2l1 project directory.
    Absolute paths wil not be changed
    """
    path = Path(*file_path)
    if path.is_absolute():
        return path
    return Path(mwr_l12l2.__file__).parent.parent / path


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
    filename_no_ext = os.path.splitext(filename)[0]
    fn_no_suffix = filename_no_ext[0:len(suffix)]
    fn_parts = fn_no_suffix.split('_')
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


if __name__ == '__main__':
    fn1 = concat_filename('L2_', '0-20000-0-06610')
    fn2 = concat_filename('L2_', '0-20000-0-06610', ext='.grb')
    fn3 = concat_filename('L2_', '0-20000-0-06610', 'A')
    fn4 = concat_filename('L2_', '0-20000-0-06610', 'A', '_testsuffix')
    fn5 = concat_filename('L2_', '0-20000-0-06610', suffix='*')
    fn6 = concat_filename('L2_', '0-20000-0-06610', suffix='*', ext='')

    dstr1 = datestr_from_filename('L2_0-20000-0-06610_A_20230828_2031.nc', '2031')
    dstr2 = datestr_from_filename('L2_0-20000-0-06610_A_20230828_2031.nc')
    # the following shall raise: dstr3 = datestr_from_filename('L2_0-20000-0-06610_A.nc')
    pass
