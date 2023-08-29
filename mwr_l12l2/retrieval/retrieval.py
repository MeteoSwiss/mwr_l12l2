import glob
import os
import shutil

import datetime as dt
import numpy as np

from mwr_l12l2.errors import MissingDataError, MWRConfigError
from mwr_l12l2.model.ecmwf.interpret_ecmwf import ModelInterpreter
from mwr_l12l2.retrieval.tropoe_helpers import model_to_tropoe
from mwr_l12l2.utils.config_utils import get_retrieval_config
from mwr_l12l2.utils.data_utils import get_from_nc_files, has_data
from mwr_l12l2.utils.file_utils import abs_file_path, concat_filename, datetime64_from_filename


class Retrieval(object):
    """Class for gathering and preparing all necessary information to run the retrieval

    Args:
        conf: configuration file or dictionary
        node: identifier for different parallel TROPoe runs. Defaults to 0.
    """

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
        self.model_prof_file_tropoe = None  # extracted model reference profiles and uncertainties (as input to TROPoe)
        self.model_sfc_file_tropoe = None  # output file for inter/extrapolation of model data to station altitude

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

        # set by choose_mode_files():
        self.model_fc_file = None
        self.model_zg_file = None

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
        self.choose_model_files()
        self.prepare_model(self.time_mean)
        # TODO launch run_tropoe.py here
        self.postprocess_tropoe()
        # TODO: adapt drawing on https://meteoswiss.atlassian.net/wiki/spaces/MDA/pages/46564537/L2+retrieval+EWC
        #  by inverting order between interpret_ecmwf and prepare_eprofile

    def prepare_paths(self):
        """prepare input and output paths and filenames from config"""
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

    def choose_model_files(self):
        """choose most actual model forecast run containing time range in MWR data and according zg file"""
        # TODO: write a test for this method

        # find forecast file
        file_pattern_fc = concat_filename(self.conf['data']['model_fc_file_prefix'], self.wigos, self.inst_id,
                                          suffix='*' + self.conf['data']['model_fc_file_suffix'],
                                          ext=self.conf['data']['model_fc_file_ext'])
        fc_files = glob.glob(os.path.join(self.conf['data']['model_dir'], file_pattern_fc))

        file_fc_youngest = None
        ts_youngest_fc = np.datetime64('1900-01-01')  # simple init to be sure to always find younger
        for file in fc_files:
            ts_fc = datetime64_from_filename(file, self.conf['data']['model_fc_file_suffix'])
            if ts_youngest_fc <= ts_fc <= self.time_min:
                ts_youngest_fc = ts_fc
                file_fc_youngest = file
        if file_fc_youngest is None:
            raise MissingDataError('found no model forecast file containing data from {}'.format(self.time_min))
        else:
            self.model_fc_file = file_fc_youngest

        # find z file with model altitude at grid points relevant to station (not expected to be dated)
        file_z = os.path.join(self.conf['data']['model_dir'],
                              concat_filename(self.conf['data']['model_z_file_prefix'], self.wigos, self.inst_id,
                                              ext=self.conf['data']['model_z_file_ext']))
        if os.path.exists(file_z):
            self.model_zg_file = file_z
        else:
            raise MissingDataError('found no model file containing model altitude grid points')

    def prepare_model(self, time):
        """extract reference profile and uncertainties as well as surface data from ECMWF to files readable by TROPoe"""
        model = ModelInterpreter(self.model_fc_file, self.model_zg_file)
        model.run(time)
        prof_data, sfc_data = model_to_tropoe(model)
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
