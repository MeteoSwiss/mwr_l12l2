import glob
import os
import shutil

import datetime as dt
import numpy as np
import xarray as xr

from mwr_l12l2.model.ecmwf.interpret_ecmwf import ModelInterpreter
from mwr_l12l2.utils.data_utils import get_from_nc_files, set_encoding, has_data
from mwr_l12l2.utils.file_uitls import abs_file_path


class Retrieval(object):

    def __init__(self, node=0):
        self.conf = {'dir_mwr_in': abs_file_path('mwr_l12l2/data/mwr/'),
                     'prefix_mwr_in': 'MWR_1C01_',
                     'dir_alc_in': abs_file_path('mwr_l12l2/data/alc/'),
                     'prefix_alc_in': 'L2_',
                     'basedir_tropoe_files': abs_file_path('mwr_l12l2/data/tropoe/'),
                     'tropoe_subfolder_basename': 'node_',
                     'mwr_filename_tropoe': 'mwr.nc',
                     'alc_filename_tropoe': 'alc.nc',
                     'model_prof_filename_tropoe': 'model_prof.nc',
                     'model_sfc_filename_tropoe': 'model_sfc.nc',
                     }
                     # TODO: put this dict to retrieval config file at retrieval_conf and set up a config reader
        self.node = node
        self.wigos = None
        self.inst_id = None
        self.tropoe_dir = None
        self.mwr_files = None
        self.alc_files = None
        self.mwr_file_tropoe = None
        self.alc_file_tropoe = None
        self.model_prof_file_tropoe = None  # model reference profiles and uncertainties to (as input to TROPoe)
        self.model_sfc_file_tropoe = None  # output file for inter/extrapolation of model data to station altitude
        self.model_fc_file = abs_file_path('mwr_l12l2/data/ecmwf_fc/ecmwf_fc_0-20000-0-10393_A_202304250000_converted_to.nc')
        self.model_zg_file = abs_file_path('mwr_l12l2/data/ecmwf_fc/ecmwf_z_0-20000-0-10393_A.grb')
        self.time_max = None
        self.time_min = None
        self.sfc_temp_obs_exists = None
        self.sfc_rh_obs_exists = None
        self.sfc_p_obs_exists = None
        self.alc_exists = None

    def run(self):
        self.prepare_paths()
        self.prepare_tropoe_dir()
        self.select_instrument()
        self.list_obs_files()
        # TODO: set earliest time to be considered by setting start_time=... in prepare_obs
        self.prepare_obs(delete_mwr_in=False)  # TODO: switch delete_mwr_in to True for operational processing
        self.prepare_model(dt.datetime(2023, 4, 25, 15, 0, 0))  # TODO select mean between min and max MWR time instead
        self.prepare_vip()
        # TODO launch run_tropoe.py here
        self.postprocess_tropoe()
        # TODO: adapt drawing on https://meteoswiss.atlassian.net/wiki/spaces/MDA/pages/46564537/L2+retrieval+EWC
        #  by inverting order between interpret_ecmwf and prepare_eprofile

    def prepare_paths(self):
        """prepare output paths and filenames from config"""
        self.tropoe_dir = os.path.join(self.conf['basedir_tropoe_files'],
                                       '{}{}/'.format(self.conf['tropoe_subfolder_basename'], self.node))
        self.mwr_file_tropoe = os.path.join(self.tropoe_dir, self.conf['mwr_filename_tropoe'])
        self.alc_file_tropoe = os.path.join(self.tropoe_dir, self.conf['alc_filename_tropoe'])
        self.model_prof_file_tropoe = os.path.join(self.tropoe_dir, self.conf['model_prof_filename_tropoe'])
        self.model_sfc_file_tropoe = os.path.join(self.tropoe_dir, self.conf['model_sfc_filename_tropoe'])

    def prepare_tropoe_dir(self):
        """set up an empty tropoe tmp file directory for the current node (remove old one if existing)"""
        if os.path.exists(self.tropoe_dir):
            shutil.rmtree(self.tropoe_dir)
        os.mkdir(self.tropoe_dir)

    def select_instrument(self):
        """select instrument which has oldest (processable) mwr file in input dir"""
        # TODO: implement this
        # TODO: Need to lock lookup for station selection for other nodes until prepare_eprofile_main with delete_mwr_in
        #       is done. Something like https://stackoverflow.com/questions/52815858/python-lock-directory might work
        self.wigos = '0-20000-0-10393'
        self.inst_id = 'A'

    def list_obs_files(self):
        """get file lists for the selected station"""
        # TODO: might want to use function from mwr_raw2l1.utils.file_utils to select also dependent on time limits
        self.mwr_files = glob.glob(os.path.join(self.conf['dir_mwr_in'],
                                       '{}*{}_{}*.nc'.format(self.conf['prefix_mwr_in'], self.wigos, self.inst_id)))
        self.alc_files = glob.glob(os.path.join(self.conf['dir_alc_in'],
                                       '{}*{}*.nc'.format(self.conf['prefix_alc_in'], self.wigos)))

    def prepare_obs(self, delete_mwr_in=False, start_time=None, end_time=None):
        """function preparing E-PROFILE MWR and ALC inputs (concatenate to one file, select time, saving)"""

        tolerance_alc_time = np.timedelta64(5, 'm')

        start_time = np.datetime64(start_time)
        end_time = np.datetime64(end_time)

        # MWR treatment
        mwr = get_from_nc_files(self.mwr_files)

        self.time_min = max(mwr.time.min(), start_time)
        self.time_max = min(mwr.time.max(), end_time)
        mwr = mwr.where((mwr.time >= self.time_min) & (mwr.time <= self.time_max), drop=True)  # brackets because of precedence of & over > and <

        mwr.to_netcdf(self.mwr_file_tropoe)
        if delete_mwr_in:
            for file in self.mwr_files:
                os.remove(file)

        if mwr.time.size == 0:
            # TODO: logger.warning; remove return. set self.mwr_exists and also alc_exists (below)
            return

        self.sfc_temp_obs_exists = has_data(mwr, 'air_temperature')  # TODO: put mwr file varnames in config
        self.sfc_rh_obs_exists = has_data(mwr, 'relative_humidity')
        self.sfc_p_obs_exists = has_data(mwr, 'air_pressure')

        # ALC treatment
        self.alc_exists = True  # start assuming ALC obs exist, set to False if not.
        if self.alc_files:  # not empty list, not None
            # careful: MeteoSwiss daily concat files have problem with calendar. Use instant files or concat at CEDA
            alc = get_from_nc_files(self.alc_files)
            alc = alc.where((alc.time >= self.time_min-tolerance_alc_time)
                            & (alc.time <= self.time_max+tolerance_alc_time), drop=True)
            alc.to_netcdf(self.alc_file_tropoe)
            if alc.time.size == 0:
                self.alc_exists = False
        else:
            self.alc_exists = False

    def prepare_model(self, time):
        """extract reference profile and uncertainties as well as surface data from ECMWF to files readable by TROPoe"""

        model = ModelInterpreter(self.model_fc_file, self.model_zg_file)
        model.run(time)

        central_lat = model.fc.latitude.values[int(len(model.fc.latitude)/2)]
        central_lon = model.fc.longitude.values[int(len(model.fc.latitude) / 2)]
        time_encoding = {'units': 'seconds since 1970-01-01', 'calendar': 'standard'}

        prof_data_specs={'base_time': dict(dims=(), data=np.datetime64('1970-01-01', 'ns')),
                         'time_offset': dict(dims='time', data=model.time_ref),
                         'lat': dict(dims=(), data=central_lat,
                                     attrs={'units': 'degrees_north'}),
                         'lon': dict(dims=(), data=central_lon,
                                     attrs={'units': 'degrees_east'}),
                         'height': dict(dims='height', data=model.z_ref/1e3,
                                        attrs={'long_name': 'Height above mean sea level', 'units': 'km'}),
                         'temperature': dict(dims=('time', 'height'), data=model.t_ref[np.newaxis, :]-273.15,
                                             attrs={'units': 'Celsius'}),
                         'sigma_temperature': dict(dims=('time', 'height'), data=model.t_err[np.newaxis, :],
                                                   attrs={'units': 'Celsius'}),
                         'waterVapor': dict(dims=('time', 'height'), data=model.q_ref[np.newaxis, :]*1e3,
                                            attrs={'units': 'g/kg'}),
                         'sigma_waterVapor': dict(dims=('time', 'height'), data=model.q_err[np.newaxis, :]*1e3,
                                                  attrs={'units': 'g/kg'}),
                         }
        prof_data_attrs = {'source': 'reference profile and uncertainties extracted from ECMWF operational forecast'}

        sfc_data_specs = {'base_time': dict(dims=(), data=np.datetime64('1970-01-01', 'ns')),
                          'time_offset': dict(dims='time', data=model.time_ref),
                          'lat': dict(dims=(), data=central_lat,
                                      attrs={'units': 'degrees_north'}),
                          'lon': dict(dims=(), data=central_lon,
                                      attrs={'units': 'degrees_east'}),
                          'height': dict(dims='height', data=model.z_ref[-1:] / 1e3,
                                         attrs={'long_name': 'Height above mean sea level', 'units': 'km'}),
                          'temperature': dict(dims=('time', 'height'), data=model.t_ref[np.newaxis, -1:] - 273.15,
                                              attrs={'units': 'Celsius'}),
                          'sigma_temperature': dict(dims=('time', 'height'), data=model.t_err[np.newaxis, -1:],
                                                    attrs={'units': 'Celsius'}),
                          'waterVapor': dict(dims=('time', 'height'), data=model.q_ref[np.newaxis, -1:] * 1e3,
                                             attrs={'units': 'g/kg'}),
                          'sigma_waterVapor': dict(dims=('time', 'height'), data=model.q_err[np.newaxis, -1:] * 1e3,
                                                   attrs={'units': 'g/kg'}),
                          }
        # TODO: important! and easy... instead of just taking lowest altitude interp/extrapolate to station_altitude
        # instead. use log for pressure
        sfc_data_attrs = {'source': 'surface quantities and uncertainties extracted from ECMWF operational forecast'}
        # TODO: add more detail on which ECMWF forecast is used to output file directly in main retrieval routine
        # (info cannot be found inside grib file). Might also want to add lat/lon area used.


        # construct datasets
        prof_data = xr.Dataset.from_dict(prof_data_specs)
        sfc_data = xr.Dataset.from_dict(sfc_data_specs)

        # add encodings and global attrs to datasets
        for ds in [prof_data, sfc_data]:  #common time encodings for all datasets
            ds = set_encoding(ds, ['base_time', 'time_offset'], time_encoding)
        prof_data.attrs = prof_data_attrs
        sfc_data.attrs = sfc_data_attrs

        # save
        prof_data.to_netcdf(self.model_prof_file_tropoe)
        sfc_data.to_netcdf(self.model_sfc_file_tropoe)

    def prepare_vip(self):
        """prepare the configuration file (vip.txt) for running the TROPoe container"""
        pass

    def postprocess_tropoe(self):
        """post-process the outputs of TROPoe and """
        pass


if __name__ == '__main__':
    ret = Retrieval()
    ret.run()
    pass
