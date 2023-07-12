import glob
import os
import shutil

import numpy as np

from mwr_l12l2.utils.data_utils import get_from_nc_files
from mwr_l12l2.utils.file_uitls import abs_file_path


class Retrieval(object):

    def __init__(self):
        self.conf = {'dir_mwr_in': abs_file_path('mwr_l12l2/data/mwr/'),
                     'prefix_mwr_in': 'MWR_1C01_',
                     'dir_alc_in': abs_file_path('mwr_l12l2/data/alc/'),
                     'prefix_alc_in': 'L2_',
                     'basedir_tropoe_files': abs_file_path('mwr_l12l2/data/tropoe/'),
                     'tropoe_subfolder_basename': 'node_',
                     'mwr_filename_tropoe': 'mwr.nc',
                     'alc_filename_tropoe': 'alc.nc',
                     }
                     # TODO: put this dict to retrieval config file at retrieval_conf and set up a config reader
        self.node = 0
        self.wigos = None
        self.inst_id = None
        self.tropoe_dir = None
        self.mwr_files = None
        self.alc_files = None
        self.mwr_file_tropoe = None
        self.alc_file_tropoe = None

    def run(self):
        self.prepare_tropoe_dir()
        self.select_instrument()
        self.list_obs_files()
        # concatenate E-Profile and deposit in node-n folder under generic name

        # TODO: set earliest time to be considered by setting start_time=... in prepare_obs
        self.prepare_obs(delete_mwr_in=False)  # TODO: switch delete_mwr_in to True for operational processing
        self.prepare_model()
        self.prepare_vip()
        # TODO launch run_tropoe.py here
        self.postprocess_tropoe()
        # TODO: adapt drawing on https://meteoswiss.atlassian.net/wiki/spaces/MDA/pages/46564537/L2+retrieval+EWC
        #  by inverting order between interpret_ecmwf and prepare_eprofile


    def prepare_tropoe_dir(self):
        """set up an empty tropoe tmp file directory for the current node (remove old one if existing)"""
        self.tropoe_dir = os.path.join(self.conf['basedir_tropoe_files'],
                                       '{}{}/'.format(self.conf['tropoe_subfolder_basename'], self.node))
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
        """function preparing E-PROFILE MWR and ALC inputs"""

        tolerance_alc_time = np.timedelta64(5, 'm')

        start_time = np.datetime64(start_time)
        end_time = np.datetime64(end_time)

        self.mwr_file_tropoe = os.path.join(self.tropoe_dir, self.conf['mwr_filename_tropoe'])
        self.alc_file_tropoe = os.path.join(self.tropoe_dir, self.conf['alc_filename_tropoe'])

        # MWR treatment
        mwr = get_from_nc_files(self.mwr_files)

        time_min = max(mwr.time.min(), start_time)
        time_max = min(mwr.time.max(), end_time)
        mwr = mwr.where((mwr.time >= time_min) & (mwr.time <= time_max), drop=True)  # brackets because of precedence of & over > and <

        mwr.to_netcdf(self.mwr_file_tropoe)
        if delete_mwr_in:
            for file in self.mwr_files:
                os.remove(file)

        if mwr.time.size == 0:
            # TODO: logger.warning; set mwr_data_exists to False
            return

        # ALC treatment
        if self.alc_files:  # not empty list, not None
            # careful: MeteoSwiss daily concat files have problem with calendar. Use instant files or concat at CEDA
            alc = get_from_nc_files(self.alc_files)
            alc = alc.where((alc.time >= time_min-tolerance_alc_time)
                            & (alc.time <= time_max+tolerance_alc_time), drop=True)
            alc.to_netcdf(self.alc_file_tropoe)

        # TODO: return time_min, time_max whether ALC data is not empty and not NaN.
        # TODO: return whether MWR has surface T, RH, p):

    def prepare_model(self):
        pass

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
