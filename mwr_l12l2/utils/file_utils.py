from pathlib import Path

import mwr_l12l2


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


if __name__ == '__main__':
    fn1 = concat_filename('L2_', '0-20000-0-06610')
    fn2 = concat_filename('L2_', '0-20000-0-06610', ext='.grb')
    fn3 = concat_filename('L2_', '0-20000-0-06610', 'A')
    fn4 = concat_filename('L2_', '0-20000-0-06610', 'A', '_testsuffix')
    fn5 = concat_filename('L2_', '0-20000-0-06610', suffix='*')
    fn6 = concat_filename('L2_', '0-20000-0-06610', suffix='*', ext='')
    pass
