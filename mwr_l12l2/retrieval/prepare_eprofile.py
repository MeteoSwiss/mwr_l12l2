import os
import numpy as np
import xarray as xr

def main(mwr_files_in, mwr_file_out, alc_files_in=None, alc_file_out=None, delete_mwr_in=False):
    """function preparing E-PROFILE MWR and ALC inputs"""

    concat_to_single_file(mwr_files_in, mwr_file_out)
    if delete_mwr_in:
        for file in mwr_files_in:
            os.remove(file)

    if alc_files_in:  # not empty list, not None
        # careful: MeteoSwiss daily concat files have problem with calendar. Use instant files or files concat at CEDA
        concat_to_single_file(alc_files_in, alc_file_out)


def concat_to_single_file(files_in, file_out, concat_dim='time'):
    """concatenate several NetCDF input files to a single NetCDF output file"""
    # TODO: find out why xarray produces all input arrays as dask array and why to_netcdf() produces warning on encoding
    x = xr.open_mfdataset(files_in, concat_dim=concat_dim, combine='nested')
    x = drop_duplicates(x, dim='time')
    x.to_netcdf(file_out)


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