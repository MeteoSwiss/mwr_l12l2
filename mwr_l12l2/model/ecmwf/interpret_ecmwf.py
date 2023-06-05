import numpy as np
import pandas as pd
import xarray as xr

from mwr_l12l2.errors import MWRInputError
from mwr_l12l2.utils.file_uitls import abs_file_path

class ModelInterpreter(object):

    def __init__(self, file_fc_nc):
        self.fc = xr.open_dataset(abs_file_path(file_fc_nc))
        self.p = None
        self.p_half = None

    def run(self, time=None):
        self.select_time(time)
        self.hybrid_to_p()
        self.p_to_z()
        self.compute_stats()
        self.produce_tropoe_file()

    def select_time(self, time):
        """reduce dataset to the time of interest (to speed up following computations)"""
        # TODO: take care to prevent dimensions using slicing rather than indexing
        pass

    def hybrid_to_p(self, file_level_coeffs=None):
        """compute pressure (in Pa) of half and full levels from hybrid levels and fill to self.p and self.p_half"""

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
        ab = np.concatenate([level_coeffs.loc[self.fc.level - 1, ['a', 'b']].to_numpy(),
                             np.expand_dims(level_coeffs.loc[self.fc.level[-1].data, ['a', 'b']].to_numpy(), axis=0)])
        a = ab[:, 0]
        b = ab[:, 1]

        # calculate pressure at model levels taking the mean between half levels
        p_surf = np.exp(self.fc.lnsp)  # for testing with pseudo std atm (p, not T/q) use p_surf=np.tile(101325,(27, 48, 3, 3))
        p_surf_all = np.tile(p_surf[:, 0:1, : , :], (1, ab.shape[0], 1, 1))  # slice instead of index to preserve dim
        a_all = np.tile(a[np.newaxis, :, np.newaxis, np.newaxis], (p_surf.shape[0], 1, p_surf.shape[2], p_surf.shape[3]))
        b_all = np.tile(b[np.newaxis, :, np.newaxis, np.newaxis], (p_surf.shape[0], 1, p_surf.shape[2], p_surf.shape[3]))
        self.p_half = a_all + b_all*p_surf_all
        self.p = (self.p_half + np.roll(self.p_half, 1, axis=1))[:, 1:,:, :] / 2

    def p_to_z(self):
        """transform pressure grid (from hybrid_to_z) to geometrical altitudes"""
        pass


    def virt_temp(self):
        """return virtual temperature from temperature and specific humdity in self.fc"""
        return self.fc.t * (1 + 0.609133*self.fc.q)

    def compute_stats(self):
        pass

    def produce_tropoe_file(self):
        pass


if __name__ == '__main__':
    x = ModelInterpreter('mwr_l12l2/data/ecmwf_fc/ecmwf_fc_0-20000-0-06610_A_202304250000_converted_to.nc')
    x.run()
    pass