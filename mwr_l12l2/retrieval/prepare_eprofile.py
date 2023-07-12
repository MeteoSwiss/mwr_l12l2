import os
import numpy as np
import xarray as xr

def main(mwr_files_in, mwr_file_out, alc_files_in=None, alc_file_out=None, delete_mwr_in=False,
         start_time=None, end_time=None):
    """function preparing E-PROFILE MWR and ALC inputs"""

    tolerance_alc_time = np.timedelta64(5, 'm')

    start_time = np.datetime64(start_time)
    end_time = np.datetime64(end_time)

    # MWR treatment
    mwr = get_data(mwr_files_in)

    time_min = max(mwr.time.min(), start_time)
    time_max = min(mwr.time.max(), end_time)
    mwr = mwr.where((mwr.time >= time_min) & (mwr.time <= time_max), drop=True)  # brackets because of precedence of & over > and <

    mwr.to_netcdf(mwr_file_out)
    if delete_mwr_in:
        for file in mwr_files_in:
            os.remove(file)

    if mwr.time.size == 0:
        # TODO: logger.warning; set mwr_data_exists to False
        return

    # ALC treatment
    if alc_files_in:  # not empty list, not None
        # careful: MeteoSwiss daily concat files have problem with calendar. Use instant files or files concat at CEDA
        alc = get_data(alc_files_in)
        alc = alc.where((alc.time >= time_min-tolerance_alc_time)
                        & (alc.time <= time_max+tolerance_alc_time), drop=True)
        alc.to_netcdf(alc_file_out)

    # TODO: return time_min, time_max whether ALC data is not empty and not NaN.
    # TODO: return whether MWR has surface T, RH, p
    # TODO: maybe best do this with an instance of class. ask Dani


def get_data(files_in, concat_dim='time'):
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