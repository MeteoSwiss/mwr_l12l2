import numpy as np
import pandas as pd
import xarray as xr

from mwr_l12l2.errors import MWRInputError
from mwr_l12l2.utils.file_uitls import abs_file_path


def hybrid_to_p(data, file_level_coeffs=None):
    if file_level_coeffs is None:
        file_level_coeffs = abs_file_path('mwr_l12l2/model/ecmwf/ecmwf_model_levels_137.csv')
    col_headers = ['level', 'a', 'b']  # expected column headers in file_level_coeffs

    # get parameters a and b for hybrid model levels from csv and do some basic input checking
    level_coeffs = pd.read_csv(file_level_coeffs)
    for name in col_headers:
        if name not in level_coeffs:
            MWRInputError("the file describing the model level coefficients at '{}' is supposed to contain a column header "
                          "'{}' in the first line".format(file_level_coeffs, name))
    if not (level_coeffs.loc[len(level_coeffs)-1, 'level'] == len(level_coeffs)-1 and level_coeffs.loc[0, 'level'] == 0):
        MWRInputError("the file describing the model level coefficients at '{}' is supposed to contain all levels "
                      'from 0 to n_levels (plus one line of column headers at the top)'.format(file_level_coeffs))

    # extract a and b parameters for levels of interest (half levels below and above)
    ab = np.concatenate([level_coeffs.loc[data.level - 1, ['a', 'b']].to_numpy(),
                         np.expand_dims(level_coeffs.loc[data.level[-1].data, ['a', 'b']].to_numpy(), axis=0)])


    # calculate pressure at model levels passing through half levels
    p_surf = np.exp(data.lnsp)
    p_half = ab[:, 0] + ab[:, 1]*p_surf[:,0,:,:]  # TODO respeat p_wurf to match each altitude in ab so that it is broadcastable
    p = (p_half + np.roll(p_half, 1)) / 2

    return p[1:]


def virt_temp(temp, q):
    return temp * (1 + 0.609133*q)


if __name__ == '__main__':
    ds = xr.open_dataset(abs_file_path('mwr_l12l2/data/ecmwf_fc/ecmwf_fc_0-20000-0-06610_A_202304250000_converted_to.nc'))
    p = hybrid_to_p(ds)
    pass