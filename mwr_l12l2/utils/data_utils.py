import numpy as np
import xarray as xr


def get_from_nc_files(files_in, concat_dim='time'):
    """read (several) NetCDF input files to a :class:`xarray.Dataset` and fix time encoding for correct nc output"""
    # TODO: find out why xarray produces all input arrays as dask array and why to_netcdf() produces warning on encoding
    data = xr.open_mfdataset(files_in, concat_dim=concat_dim, combine='nested')
    data = drop_duplicates(data, dim=concat_dim)

    # correct time encoding (especially units) which is broken by open_mfdateset by explicitly loading first file
    data_first = xr.open_dataset(files_in[0])
    data.time.encoding = data_first.time.encoding

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
