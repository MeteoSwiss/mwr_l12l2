import numpy as np
import pandas as pd
import xarray as xr

from mwr_l12l2.errors import MWRInputError
from mwr_l12l2.utils.file_uitls import abs_file_path





class ModelInterpreter(object):

    def __init__(self, file_fc_nc, file_z_grb, file_out):
        self.file_fc_nc = abs_file_path(file_fc_nc)
        self.file_z_grb = abs_file_path(file_z_grb)
        self.file_out = abs_file_path(file_out)
        self.fc = None
        self.z_surf = None
        self.p = None
        self.p_half = None
        self.z = None
        self.z_ref = None  # reference geometrical altitude profile (1d)
        self.q_ref = None  # reference humidity profile (1d)
        self.t_ref = None  # reference temperature profile (1d)
        self.q_err = None  # standard deviation of humidity profile within lat/lon area (1d)
        self.t_err = None  # standard deviation of humidity profile within lat/lon area (1d)

    def run(self, time):
        """run for data closest to selected time (in datetime64)"""
        self.load_data(time)
        self.hybrid_to_p()
        self.p_to_z()
        self.compute_stats()
        self.produce_tropoe_file()

    def load_data(self, time):
        """load dataset and reduce to the time of interest (to speed up following computations)"""
        fc_all = xr.open_dataset(self.file_fc_nc)
        self.fc = fc_all.sel(time=[np.datetime64(time)], method='nearest')  # conserve dimension using slicing
        self.z_surf = xr.open_dataset(self.file_z_grb, engine='cfgrib')


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
                             np.expand_dims(level_coeffs.loc[self.fc.level[-1].values, ['a', 'b']].to_numpy(), axis=0)])
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
        """transform pressure grid (from hybrid_to_z) to geometrical altitudes

        according to: https://confluence.ecmwf.int/display/CKB/ERA5%3A+compute+pressure+and+geopotential+on+model+levels%2C+geopotential+height+and+geometric+height
        """

        gas_const = 287.06  # gas constant for dry air (Rd)
        g = 9.80665  # gravitational acceleration of Earth

        # TODO: check whole function with hypsometric equation and possibly re-write from scratch using it (clearer)
        # TODO: check correct order in substraction/division for dp/dlogp.. problem with uppermost level
        dp = (self.p_half - np.roll(self.p_half, 1, axis=1))[:, 1:, :, :]
        dlogp = np.log( self.p_half / np.roll(self.p_half, 1, axis=1))[:, 1:, :, :]
        alpha = 1 - (self.p_half[:, 1:, :, :] / dp) * dlogp

        # correct for uppermost level
        dlogp[:, 0, :, :] = np.log(self.p_half[:, 1, :, :] / 0.1)
        alpha[:, 0, :, :] = np.tile(np.log(2), (self.p_half.shape[0], 1, self.p_half.shape[2], self.p_half.shape[3]))

        # transformation to z
        dzg_half = self.virt_temp() * gas_const * dlogp  # diff between geopotential height half levels
        zg_surf_all = self.z_surf.z.values[np.newaxis, np.newaxis, :, :] * g
        dzg_half_with_sfc = np.concatenate((dzg_half, zg_surf_all), axis=1)
        zg_half = np.flip(np.cumsum(np.flip(dzg_half_with_sfc, axis=1), axis=1), axis=1)  # integrate from surface
        zg = zg_half[:, 1:, :, :] - alpha*gas_const*self.virt_temp()

        self.z = zg / g

    def compute_stats(self):
        """take reference profiles and uncertainty"""
        # take profiles at centre of lat/lon (at last time selected) as reference
        self.z_ref = get_ref_profile(self.z)
        self.q_ref = get_ref_profile(self.fc.q)
        self.t_ref = get_ref_profile(self.fc.t)

        # take std over lat/lon (at last time selected) as error
        self.q_err = get_std_profile(self.fc.q)
        self.t_err = get_std_profile(self.fc.t)

    def produce_tropoe_file(self):
        """write reference profile and associated error to output file readable by TROPoe"""
        pass

    def virt_temp(self):
        """return virtual temperature from temperature and specific humdity in self.fc"""
        return self.fc.t * (1 + 0.609133*self.fc.q)


def get_ref_profile(x):
    """extract ref profile (last time, centre lat/lon) from a :class:`xarray.DataArray` with dim (time,level,lat,lon)"""
    return x.values[-1, :, int(x.shape[-2]/2), int(x.shape[-1]/2)]

def get_std_profile(x):
    """extract std profile (last time, std in lat/lon) from a :class:`xarray.DataArray` with dim (time,level,lat,lon)"""
    # flatten lat and lon so that we can take std over all profiles in lat/lon box
    x_flat = x.values[-1, :, :, :, ].reshape((-1, x.shape[-2] * x.shape[-1]))
    return np.std(x_flat, axis=1)

    # the following trying to interpolate q and t to same altitude grid using scipy's failed with all NaN
    # from scipy.interpolate import griddata
    # z_flat = self.z.values[-1, :, :, :, ].reshape((-1, self.z.values.shape[-2] * self.z.values.shape[-1]))
    # q_interp = griddata(z_flat[:-1, :], q_flat[:-1, :], np.tile(self.z_ref.values[:-1,np.newaxis],
    #       (1, self.fc.t.values.shape[-2] * self.fc.t.values.shape[-1])))


if __name__ == '__main__':
    import datetime as dt
    model = ModelInterpreter('mwr_l12l2/data/ecmwf_fc/ecmwf_fc_0-20000-0-06610_A_202304250000_converted_to.nc',
                             'mwr_l12l2/data/ecmwf_fc/z_ecmwf_fc_0-20000-0-10393_A.grb',
                             'mwr_l12l2/data/ecmwf_fc/model_stats_0-20000-0-06610_A_202304250000.csv')
    model.run(dt.datetime(2023, 4, 25, 15, 0, 0))
    pass