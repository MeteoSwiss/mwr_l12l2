import glob
import os
import shutil

import prepare_eprofile
from mwr_l12l2.utils.file_uitls import abs_file_path


class Retrieval(object):

    def __init__(self):
        self.conf = {'dir_mwr_in': abs_file_path('mwr_l12l2/data/mwr/'),
            'prefix_mwr_in': 'MWR_1C01_',
            'dir_alc_in': abs_file_path('mwr_l12l2/data/alc/'),
            'prefix_alc_in': 'L2_',
            'basedir_tropoe_files': abs_file_path('mwr_l12l2/data/tropoe/'),
            'tropoe_subfolder_basename': 'node_'}
            # TODO: put this dict to retrieval config file at retrieval_conf and set up a config reader
        self.node = 0
        self.wigos = None
        self.inst_id = None
        self.tropoe_dir = None
        self.mwr_files = None
        self.alc_files = None

    def run(self):
        self.prepare_tropoe_dir()
        self.select_instrument()
        self.list_obs_files()
        # concatenate E-Profile and deposit in node-n folder under generic name
        prepare_eprofile.main(self.mwr_files, os.path.join(self.tropoe_dir, 'MWR.nc'),
                              self.alc_files, os.path.join(self.tropoe_dir, 'ALC.nc'),
                              delete_mwr_in=False)  # TODO: switch delete_mwr_in to True for operational processing
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
        self.mwr_files = glob.glob(os.path.join(self.conf['dir_mwr_in'],
                                       '{}*{}_{}*.nc'.format(self.conf['prefix_mwr_in'], self.wigos, self.inst_id)))
        self.alc_files = glob.glob(os.path.join(self.conf['dir_alc_in'],
                                       '{}*{}*.nc'.format(self.conf['prefix_alc_in'], self.wigos)))

    def prepare_model(self):
        pass

    def prepare_vip(self):
        """prepare the configuration file (vip.txt) for running the TROPoe container"""
        pass

    def postprocess_tropoe(self):
        """postprocess the outputs of TROPoe and """
        pass





if __name__ == '__main__':
    ret = Retrieval()
    ret.run()
    pass