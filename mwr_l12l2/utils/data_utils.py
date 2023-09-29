import numpy as np
import pandas as pd
import xarray as xr


def get_from_nc_files(files_in, concat_dim='time'):
    """read (several) NetCDF input files to a :class:`xarray.Dataset` and fix time encoding for correct nc output"""
    data = xr.open_mfdataset(files_in, concat_dim=concat_dim, combine='nested')
    data = drop_duplicates(data, dim=concat_dim)

    # correct time encoding (especially units) which is broken by open_mfdateset by explicitly loading first file
    data_first = xr.open_dataset(files_in[0])
    data = set_encoding(data, ['time'], data_first.time.encoding)

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


def lists_to_np(indict):
    """transform all values of a dict with type list to a :class:`numpy.ndarray`"""
    for key, val in indict.items():
        if isinstance(val, list):
            indict[key] = np.array(val)
    return indict
