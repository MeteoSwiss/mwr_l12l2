import numpy as np
import pandas as pd
import xarray as xr


def get_from_nc_files(files_in, concat_dim='time'):
    """Read a list of MWR L1 E-Profile files and return a xarray dataset"""

    # Create a list of datasets
    ds_list = []
    for f in files_in:
        ds_list.append(xr.open_dataset(f, engine='h5netcdf'))
    # Concatenate the list of datasets
    data = xr.concat(ds_list, data_vars='all', dim=concat_dim)
    # Identify duplicated time values
    _, index = np.unique(data.time, return_index=True)
    # Keep only the unique time values
    data = data.isel(time=index)
    # Sort the dataset by time
    data = data.sortby(concat_dim)
    return data

def drop_duplicates(ds, dim):
    """drop duplicates from all data in ds for duplicates in dimension vector

    Args:
        ds: :class:`xarray.Dataset` or :class:`xarray.DataArray` containing the data
        dim: string indicating the dimension name to check for duplicates
    Returns:
        ds with unique dimension vector
    """

    _, ind = np.unique(ds[dim], return_index=True)  # keep first index but assume duplicate values identical anyway
    return ds.isel({dim: ind})


def set_encoding(ds, vars, enc):
    """(re-)set encoding of variables in a dataset

    Args:
        ds: :class:`xarray.Dataset` containing the data
        vars: list of variables for which encoding is to be adapted
        enc: encoding dictionary (containing e.g. units) that encoding of the respective variables shall to be set to.
    Returns:
        ds with updated encoding for var in :obj:`vars`
    """
    for var in vars:
        ds[var].encoding = enc
    return ds


def get_nearest(data, find_vals):
    """find values in data nearest values in the input data"""
    x = np.unique(data)
    out = []
    for fv in find_vals:
        out.append(x[np.abs(x-fv).argmin()])
    return out


def has_data(ds, var):
    """check if a variable in a :class:`xarray.Dataset` exists and contains non-NaN data"""
    if var in ds and not ds[var].isnull().all():
        return True
    else:
        return False


def datetime64_to_str(x, date_format):
    """transform :class:`numpy.datetime64` to a datestring corresponding to 'date_format'

    Args:
        x: datetime as :class:`numpy.datetime64` object
        date_format: date format understood by :class:`datetime.datetime`
    """
    t = pd.to_datetime(x)
    return t.strftime(date_format)


def datetime64_to_hour(x):
    """transform :class:`numpy.datetime64` to a float representing time of day in hours"""
    date_format = '%H:%M:%S.%f'
    hour_frac = np.array([1, 60, 3600])
    dstr = datetime64_to_str(x, date_format)
    hms = np.array(list(map(float, dstr.split(':'))))
    return np.sum(hms / hour_frac)


def scalars_to_time(ds, variables, time_dim='time'):
    """expand scalar variables onto time dimension to form an array of len(time) containing identical values

    Args:
        ds: :class:`xarray.Dataset` containing all requested scalar variables and the time dimension to transform to
        variables: list of variables to expand onto the time dimension. These will be replaced in-place
        time_dim (optional): name of the time dimension. Defaults to 'time'.
    """
    for var in variables:
        ds.update({var: (time_dim, ds[var].values * np.ones(ds[time_dim].shape))})
    return ds

def vectors_to_time(ds, variables, time_dim='time'):
    """expand constant vector variables onto time dimension to form an array of len(time) containing identical values
    TODO: merge with scalars_to_time

    Args:
        ds: :class:`xarray.Dataset` containing all requested scalar variables and the time dimension to transform to
        variables: list of variables to expand onto the time dimension. These will be replaced in-place
        time_dim (optional): name of the time dimension. Defaults to 'time'.
    """
    for var in variables:
        ds[var] = ds[var].expand_dims(time=ds[time_dim])
    return ds

def lists_to_np(indict):
    """transform all values of a dict with type list to a :class:`numpy.ndarray`"""
    for key, val in indict.items():
        if isinstance(val, list):
            indict[key] = np.array(val)
    return indict

def setbit(x, nth_bit):
    """set n-th bit (i.e. set to 1) in an integer or array of integers
    Function taken from Rolf's mwr_raw2l1 code. It is used to set quality flags in the retrieval output.

    Args:
        x: integer or :class:`numpy.ndarray` of integers
        nth_bit: position of bit to be set (0, 1, 2, ..)
    Returns:
        integer or array of integers where n-th bit is set while all other bits are kept as in input x
    Examples:
        >>> setbit(0, 1)
            2
        >>> setbit(3, 2)
            7
    """
    if nth_bit < 0:
        raise ValueError('position of bit cannot be negative')
    mask = 1 << nth_bit
    return x | mask


def decode_bit_flags(x):
    """decode bit encoded quality flags to a dict of boolean flags for each bit position

    Args:
        x: integer or :class:`numpy.ndarray` of integers containing the bit encoded flags
    Returns:
        dict of boolean flags for each bit position. The keys are 'bit_0', 'bit_1', etc. and the values are boolean arrays indicating whether the respective bit is set in the input x.
    """
    max_bit = int(np.ceil(np.log2(np.max(x)+1)))  # maximum bit position to check based on the maximum value in x
    # extract the
    flag_meanings = x.attrs.get('flag_meanings', ' ').split()  # get flag meanings from attributes, separated by space.
    flag_activated = []
    
    # transform binary_str to list of boolean flags for each bit position:
    for i in range(max_bit):
        bit_flag = (x.values.astype('int').item() >> i) & 1
        if bit_flag:
            flag_activated.append(flag_meanings[i] if i < len(flag_meanings) else f'bit_{i}')
    
    return flag_activated

