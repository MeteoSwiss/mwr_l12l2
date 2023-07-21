import glob
import os
import shutil

import datetime as dt
import numpy as np
import xarray as xr

from mwr_l12l2.errors import MissingDataError, MWRConfigError
from mwr_l12l2.model.ecmwf.interpret_ecmwf import ModelInterpreter
from mwr_l12l2.utils.config_utils import get_retrieval_config
from mwr_l12l2.utils.data_utils import get_from_nc_files, set_encoding, has_data
from mwr_l12l2.utils.file_uitls import abs_file_path


class Retrieval(object):

    def __init__(self, conf, node=0):
        if isinstance(conf, dict):
            self.conf = conf
        elif os.path.isfile(conf):
            self.conf = get_retrieval_config(conf)
        else:
            raise MWRConfigError("The argument 'conf' must be a conf dictionary or a path pointing to a config file")

        self.node = node

        # set by prepare_pahts():
        self.tropoe_dir = None
        self.mwr_file_tropoe = None
        self.alc_file_tropoe = None
        self.model_prof_file_tropoe = None  # model reference profiles and uncertainties to (as input to TROPoe)
        self.model_sfc_file_tropoe = None  # output file for inter/extrapolation of model data to station altitude
        self.model_fc_file = abs_file_path('mwr_l12l2/data/ecmwf_fc/ecmwf_fc_0-20000-0-10393_A_202304250000_converted_to.nc')  # TODO: include to conf
        self.model_zg_file = abs_file_path('mwr_l12l2/data/ecmwf_fc/ecmwf_z_0-20000-0-10393_A.grb')  # TODO: include to conf with dir and basename

        # set by select_instrument():
        self.wigos = None
        self.inst_id = None

        # set by list_obs():
        self.mwr_files = None
        self.alc_files = None

        # set by prepare_obs():
        self.time_min = None  # min time of MWR observations available and considered
        self.time_max = None  # max time of MWR observations available and considered
        self.time_mean = None  # average time of period containing considered MWR observations
        self.sfc_temp_obs_exists = None  # is temperature measured by met station of MWR instrument?
        self.sfc_rh_obs_exists = None  # is rel humidity measured by met station of MWR instrument?
        self.sfc_p_obs_exists = None  # is pressure measured by met station of MWR instrument?
        self.alc_exists = None  # is cloud base measured by co-located ceilometer?

    def run(self, start_time=None, end_time=None):
        """run the entire retrieval chain

        Args:
            start_time (optional): earliest time from which to consider data. If not specified, all data younger than
                'max_age' specified in retrieval config will be used or, if 'max_age' is None, age of data is unlimited.
            end_time (optional): latest time from which to consider data. If not specified, all data received by now is
                processed.
        """
        if start_time is None and self.conf['data']['max_age'] is not None:
            start_time = dt.datetime.utcnow()-dt.timedelta(minutes=self.conf['data']['max_age'])
        # end_time/start_time can be left at None to consider latest/earliest available MWR data

        self.prepare_paths()
        self.prepare_tropoe_dir()
        self.select_instrument()  # TODO: select_instrument and list_obs_files would better be externalised
        self.list_obs_files()
        self.prepare_obs(start_time=start_time, end_time=end_time, delete_mwr_in=False)  # TODO: switch delete_mwr_in to True for operational processing
        self.prepare_model(self.time_mean)
        # TODO launch run_tropoe.py here
        self.postprocess_tropoe()
        # TODO: adapt drawing on https://meteoswiss.atlassian.net/wiki/spaces/MDA/pages/46564537/L2+retrieval+EWC
        #  by inverting order between interpret_ecmwf and prepare_eprofile

    def prepare_paths(self):
        """prepare output paths and filenames from config"""
        self.tropoe_dir = os.path.join(self.conf['data']['tropoe_basedir'],
                                       '{}{}/'.format(self.conf['data']['tropoe_subfolder_basename'], self.node))
        self.mwr_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['mwr_filename_tropoe'])
        self.alc_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['alc_filename_tropoe'])
        self.model_prof_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['model_prof_filename_tropoe'])
        self.model_sfc_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['model_sfc_filename_tropoe'])

    def prepare_tropoe_dir(self):
        """set up an empty tropoe tmp file directory for the current node (remove old one if existing)"""
        if os.path.exists(self.tropoe_dir):
            shutil.rmtree(self.tropoe_dir)
        os.mkdir(self.tropoe_dir)

    def select_instrument(self):
        """select instrument which has oldest (processable) mwr file in input dir"""
        # TODO: implement this
        # TODO: Need to lock lookup for station selection for other nodes until prepare_eprofile_main with delete_mwr_in
        #       is done. Something like https://stackoverflow.com/questions/52815858/python-lock-directory might work.
        #       but better use ecflow to not data listing for other nodes until end of prepare_eprofile_main
        self.wigos = '0-20000-0-10393'
        self.inst_id = 'A'

    def list_obs_files(self):
        """get file lists for the selected station

        Note:
             this method shall list all (MWR) files not just the ones matching time settings. Like that old (obsolete)
             files are removed when :meth:`prepare_obs` is run with delete_mwr_in=True
        """
        self.mwr_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                                '{}*{}_{}*.nc'.format(self.conf['data']['mwr_file_prefix'],
                                                                      self.wigos, self.inst_id)))
        self.alc_files = glob.glob(os.path.join(self.conf['data']['alc_dir'],
                                                '{}*{}*.nc'.format(self.conf['data']['alc_file_prefix'], self.wigos)))
        if not self.mwr_files:
            err_msg = ('No MWR data for {} {} found in {}. These files must have been removed between station selection'
                       ' and file listing. This should not happen!'.format(self.wigos, self.inst_id,
                                                                           self.conf['data']['mwr_dir']))
            # TODO: also add a CRITICAL entry with err_msg to logger before raising the exception
            raise MissingDataError(err_msg)

    def prepare_obs(self, start_time=None, end_time=None, delete_mwr_in=False):
        """function preparing E-PROFILE MWR and ALC inputs (concatenate to one file, select time, saving)"""

        tolerance_alc_time = np.timedelta64(5, 'm')  # get ALC up to 5 minutes before/after start/end of MWR interval

        start_time = np.datetime64(start_time)
        end_time = np.datetime64(end_time)

        # MWR treatment
        mwr = get_from_nc_files(self.mwr_files)

        self.time_min = max(mwr.time.min().values, start_time)
        self.time_max = min(mwr.time.max().values, end_time)
        self.time_mean = self.time_min + (self.time_max-self.time_min)/2  # need to work with diff to get timedelta
        mwr = mwr.where((mwr.time >= self.time_min) & (mwr.time <= self.time_max), drop=True)  # brackets because of precedence of & over > and <

        mwr.to_netcdf(self.mwr_file_tropoe)
        if delete_mwr_in:
            for file in self.mwr_files:
                os.remove(file)

        if mwr.time.size == 0:  # this must happen after file deletion
            raise MissingDataError('None of the MWR files found for {} {} contains data between the required time '
                                   'limits (min={}; max={})'.format(self.wigos, self.inst_id, start_time, end_time))

        self.sfc_temp_obs_exists = has_data(mwr, 'air_temperature')
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
    ret = Retrieval(abs_file_path('mwr_l12l2/config/retrieval_config.yaml'))
    ret.run(start_time=np.datetime64('2023-04-25 00:00:00'))
    pass
