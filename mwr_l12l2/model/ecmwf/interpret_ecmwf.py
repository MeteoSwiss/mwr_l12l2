import os

import numpy as np
import pandas as pd
import xarray as xr

from mwr_l12l2.log import logger
from mwr_l12l2.errors import MWRInputError
from mwr_l12l2.utils.file_utils import abs_file_path
from mwr_l12l2.utils.data_utils import datetime64_to_str

class ModelInterpreter(object):
    """class to interpret model data from ECMWF and produce input files for TROPoe

    Args:
        file_fc_nc: file containing forecast data in NetCDF. Must have been converted from grib to nc with
            mwr_l12l2/model/ecmwf/grb_to_nc.sh before. Direct read-in of grib doesn't work because of dim of lnsp
        file_zg_grb: file containing the geopotential of the lowest model level in grib format
        station_altitude (optional): Station altitude to inter/extrapolate model data to for sfc data.
            If not specified the lowest model level will be used for surface data.
        file_ml (optional): a and b parameters to transform model levels to pressure and altitude grid.
            If not specified the file named 'ecmwf_model_levels_137.csv' in same dir as interpret_ecmwf.py will be used.
    """

    def __init__(self, file_fc_nc, file_zg_grb=None, station_altitude=None, file_ml=None):

        self.file_fc_nc = abs_file_path(file_fc_nc)
        # TODO: check if geopotential from forecast is really equivalent to geopotential from analysis and if is does not crash MARS request
        # if file_zg_grb is not None:
        #     self.use_zg_from_fc = False
        #     self.file_zg_grb = abs_file_path(file_zg_grb)
        # else:
        #     self.use_zg_from_fc = True
        self.use_zg_from_fc = False
        self.file_zg_grb = abs_file_path(file_zg_grb)
        self.station_altitude = station_altitude
        self.file_ml = file_ml
        if self.file_ml is None:
            self.file_ml = os.path.join(os.path.dirname(__file__), 'ecmwf_model_levels_137.csv')
        self.fc = None
        self.zg_surf = None
        self.p = None
        self.p_half = None
        self.z = None
        self.time_ref = None  # time of reference profiles
        self.z_ref = None  # reference geometrical altitude profile (1d)
        self.p_ref = None  # reference pressure profile (1d)
        self.q_ref = None  # reference humidity profile (1d)
        self.t_ref = None  # reference temperature profile (1d)
        self.q_err = None  # standard deviation of humidity profile within lat/lon area (1d)
        self.t_err = None  # standard deviation of humidity profile within lat/lon area (1d)

    def run(self, time_min, time_max):
        """run for data closest to selected time in :class:`numpy.datetime64` or :class:`datetime.datetime`"""
        self.load_data(time_min, time_max)
        self.hybrid_to_p()
        self.p_to_z()
        self.compute_stats()

    def load_data(self, time_min, time_max):
        """load dataset and reduce to the time of interest (to speed up following computations)"""
        fc_all = xr.open_dataset(self.file_fc_nc)
        if time_max - time_min > np.timedelta64(1, 'h'):
            self.fc = fc_all.sel(time=slice(time_min, time_max))
        else:
            self.fc = fc_all.sel(time=slice(time_min, time_min+np.timedelta64(1,'h')))

        logger.info('Using forecast data between '+datetime64_to_str(self.fc.time.min().values, '%Y-%m-%d %H:%M:%S')+' and '+datetime64_to_str(self.fc.time.max().values, '%Y-%m-%d %H:%M:%S'))

        # Now keeping all models runs between time_min and time_max of the mwr observations, TROPoe does the interpolation
        if not self.use_zg_from_fc:
            logger.info('Reading geopotential from analysis data')
            self.zg_surf = xr.open_dataset(self.file_zg_grb, engine='cfgrib')

    def hybrid_to_p(self):
        """compute pressure (in Pa) of half and full levels from hybrid levels and fill to self.p and self.p_half"""

        col_headers = ['level', 'a', 'b']  # expected column headers in self.file_ml

        # get parameters a and b for hybrid model levels from csv and do some basic input checking
        level_coeffs = pd.read_csv(self.file_ml)
        for name in col_headers:
            if name not in level_coeffs:
                MWRInputError("the file describing the model level coefficients at '{}' is supposed to contain "
                              "a column header '{}' in the first line".format(self.file_ml, name))
        if not (level_coeffs.loc[len(level_coeffs)-1, 'level'] == len(level_coeffs)-1
                and level_coeffs.loc[0, 'level'] == 0):
            MWRInputError("the file describing the model level coefficients at '{}' is supposed to contain all levels "
                          'from 0 to n_levels (plus one line of column headers at the top)'.format(self.file_ml))

        # extract a and b parameters for levels of interest (half levels below and above)
        ab = np.concatenate([level_coeffs.loc[self.fc.level - 1, ['a', 'b']].to_numpy(),
                             np.expand_dims(level_coeffs.loc[self.fc.level[-1].values, ['a', 'b']].to_numpy(), axis=0)])
        a = ab[:, 0]
        b = ab[:, 1]

        # calculate pressure at model levels taking the mean between half levels
        p_surf = np.exp(self.fc.lnsp)  # to test pseudo std atm (p, not T/q) use p_surf=np.tile(101325,(27, 48, 3, 3))
        p_surf_all = np.tile(p_surf[:, 0:1, :, :], (1, ab.shape[0], 1, 1))  # slice instead of index to preserve dim
        a_all = np.tile(a[np.newaxis, :, np.newaxis, np.newaxis],
                        (p_surf.shape[0], 1, p_surf.shape[2], p_surf.shape[3]))
        b_all = np.tile(b[np.newaxis, :, np.newaxis, np.newaxis],
                        (p_surf.shape[0], 1, p_surf.shape[2], p_surf.shape[3]))
        self.p_half = a_all + b_all*p_surf_all
        self.p = (self.p_half + np.roll(self.p_half, 1, axis=1))[:, 1:, :, :] / 2

    def p_to_z(self):
        """transform pressure grid (from :meth:`hybrid_to_p`) to geometrical altitudes

        according to: https://confluence.ecmwf.int/display/CKB/ERA5%3A+compute+pressure+and+geopotential+on+model+levels%2C+geopotential+height+and+geometric+height
        """  # noqa: E501

        gas_const = 287.06  # gas constant for dry air (Rd)
        g = 9.80665  # gravitational acceleration of Earth

        # TODO: check whole function with hypsometric equation and possibly re-write from scratch using it (clearer)
        # TODO: get rid of RuntimeWarning: divide by zero encountered in log
        dp = (self.p_half - np.roll(self.p_half, 1, axis=1))[:, 1:, :, :]
        dlogp = np.log(self.p_half / np.roll(self.p_half, 1, axis=1))[:, 1:, :, :]
        alpha = 1 - (self.p_half[:, 1:, :, :] / dp) * dlogp

        # correct for uppermost level
        dlogp[:, 0, :, :] = np.log(self.p_half[:, 1, :, :] / 0.1)
        alpha[:, 0, :, :] = np.tile(-np.log(2), (self.p_half.shape[0], self.p_half.shape[2], self.p_half.shape[3]))

        # transformation to geopotential height zg
        dzg_half = self.virt_temp() * gas_const * dlogp  # diff between geopotential height half levels
        if not self.use_zg_from_fc:
            zg_surf_all = np.tile(self.zg_surf.z.values,(self.p_half.shape[0], 1, 1, 1)) #self.zg_surf.z.values[np.newaxis, np.newaxis, :, :]
        else:
            # New version to work with geopotential from the fc directly:
            zg_surf_all = np.expand_dims(self.fc.z.isel(level=0).data,1)
        dzg_half_with_sfc = np.concatenate((dzg_half, zg_surf_all), axis=1)
        zg_half = np.flip(np.cumsum(np.flip(dzg_half_with_sfc, axis=1), axis=1), axis=1)  # integrate from surface
        zg = zg_half[:, 1:, :, :] - alpha*gas_const*self.virt_temp()

        # transformation to geometrical height z
        self.z = zg / g

    def compute_stats(self):
        """take reference profiles and uncertainty"""
        # TODO: make this method more generic
        # take profiles at centre of lat/lon (at last time selected) as reference
        self.z_ref = get_ref_profile(self.z)
        self.q_ref = get_ref_profile(self.fc.q)
        self.t_ref = get_ref_profile(self.fc.t)
        self.p_ref = get_ref_profile(self.p)
        self.time_ref = self.fc.time.values

        # Compute reference profile of RH
        self.rh = self.relative_humidity()
        
        # take std over lat/lon (at last time selected) as error
        self.q_err = get_std_profile(self.fc.q)
        self.t_err = get_std_profile(self.fc.t)

    def virt_temp(self):
        """return virtual temperature from temperature and specific humidity in self.fc"""
        return self.fc.t * (1 + 0.609133*self.fc.q)
    
    def relative_humidity(self):
        """return relative humidity from pressure, specific humitiy and temperature in self.rh according to https://codes.ecmwf.int/grib/param-db/?id=157"""        
        # Mixed phased parameter (depends on T):
        alpha = ((self.t_ref - 250.16)/(273.16-250.16))**2
        alpha[self.t_ref<250.16] = 0
        alpha[self.t_ref>273.16] = 1

        # Saturation vapor pressure
        esat_w = 611.21*np.exp(17.502*((self.t_ref - 273.16) / (self.t_ref -32.19)))
        esat_i = 611.21*np.exp(22.587*((self.t_ref - 273.16) / (self.t_ref +0.7)))
        esat = alpha*esat_w + (1-alpha)*esat_i

        # Ratio between molar masses of water and dry air
        epsilon = 0.621981

        # relative humity
        return self.p_ref*self.q_ref*(1/epsilon)/(esat*(1 + self.q_ref*(1/epsilon - 1)))

def get_ref_profile(x):
    """extract ref profile (last time, centre lat/lon) from a :class:`xarray.DataArray` with dim (time,level,lat,lon)"""
    if type(x) is not np.ndarray:
        x = x.values
    return x[:, :, int(x.shape[-2]/2), int(x.shape[-1]/2)]  # CARE: if you edit, also edit central_lat/lon in writer


def get_std_profile(x):
    """extract std profile (last time, std in lat/lon) from a :class:`xarray.DataArray` with dim (time,level,lat,lon)"""
    # flatten lat and lon so that we can take std over all profiles in lat/lon box
    #x_flat = x.values[-1, :, :, :, ].reshape((-1, x.shape[-2] * x.shape[-1]))
    #return np.std(x_flat, axis=1)
    # TODO: Check if we should include the time dimension to get more realistic std dev ?
    return x.std(dim=['latitude','longitude']).data

    # the following trying to interpolate q and t to same altitude grid using scipy's failed with all NaN
    # from scipy.interpolate import griddata (possibly only because z-grid was not monotonic at this time)
    # z_flat = self.z.values[-1, :, :, :, ].reshape((-1, self.z.values.shape[-2] * self.z.values.shape[-1]))
    # q_interp = griddata(z_flat[:-1, :], q_flat[:-1, :], np.tile(self.z_ref.values[:-1,np.newaxis],
    #       (1, self.fc.t.values.shape[-2] * self.fc.t.values.shape[-1])))


if __name__ == '__main__':
    import datetime as dt
    model = ModelInterpreter('mwr_l12l2/data/ecmwf_fc/ecmwf_fc_0-20000-0-10393_A_202304250000_converted_to.nc',
                             'mwr_l12l2/data/ecmwf_fc/ecmwf_z_0-20000-0-10393_A.grb',
                             'mwr_l12l2/data/output/ecmwf/model_stats_0-20000-0-10393_A_202304251500.nc',
                             'mwr_l12l2/data/output/ecmwf/model_sfc_0-20000-0-10393_A_202304251500.nc',
                             127)
    model.run(dt.datetime(2023, 4, 25, 15, 0, 0))
    pass
