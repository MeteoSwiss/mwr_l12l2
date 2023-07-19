import os.path
import shutil
import unittest

import numpy as np

from mwr_l12l2.errors import MWRTestError
from mwr_l12l2.retrieval.retrieval import Retrieval
from mwr_l12l2.utils.file_uitls import abs_file_path


mwr_dir = abs_file_path('tests/data/mwr/')
mwr_basename = 'MWR_1C01_0-20000-0-10393_A'
mwr_ext = '.nc'
alc_dir = abs_file_path('tests/data/alc/')
alc_basename = 'L2_0-20000-0-10393_0'
alc_ext = '.nc'

dir_out = abs_file_path('tests/data/output/')
mwr_file_out = os.path.join(dir_out, 'mwr.nc')
alc_file_out = os.path.join(dir_out, 'alc.nc')

class TestRetrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """copy example files to the test config directory

        By doing this here, one would find out for permission issues right at set up instead of causing a failed test.
        """
        if os.path.exists(dir_out):
            err_msg = ("directory '{}' is supposed to be created during run of config tests, but should not be there"
                       " when '{}' starts. Please remove it manually (making sure that you don't erase data you might"
                       " still need) and run tests again".format(dir_out, __file__))
            raise MWRTestError(err_msg)
        os.mkdir(dir_out)

    @classmethod
    def tearDownClass(cls):
        """remove test config directory again"""
        shutil.rmtree(dir_out)
    def setUp(self):
        self.ret = Retrieval(abs_file_path('mwr_l12l2/config/retrieval_config.yaml'))

    def test_prepare_obs(self):
        self.ret.mwr_files = [os.path.join(mwr_dir, mwr_basename + '202304251300' + mwr_ext),
                              os.path.join(mwr_dir, mwr_basename + '202304251400' + mwr_ext),
                              os.path.join(mwr_dir, mwr_basename + '202304251500' + mwr_ext)]
        expected_mean_time = np.datetime64('2023-04-25 14:30:00')
        expected_mwr_met_existence = {'sfc_temp_obs_exists': True, 'sfc_p_obs_exists': True, 'sfc_rh_obs_exists': False}
        self.ret.alc_files = [os.path.join(alc_dir, alc_basename + '20230425' + alc_ext)]
        expected_alc_file_existence = True
        self.ret.mwr_file_tropoe = mwr_file_out
        self.ret.alc_file_tropoe = alc_file_out

        with self.subTest(operation='run main'):
            self.ret.prepare_obs()
        with self.subTest(operation='check data times'):
            self.assertTrue(np.abs(self.ret.time_mean - expected_mean_time) < np.timedelta64(10, 'm'))
        with self.subTest(operation='check vars/files existence status'):
            self.assertEqual(self.ret.alc_exists, expected_alc_file_existence,
                             msg='ALC data existence is expected to be {} but retrieval class says {}'.format(
                                 expected_alc_file_existence, self.ret.alc_exists))
            for key, val in expected_mwr_met_existence.items():
                self.assertEqual(getattr(self.ret, key), val,
                                 msg='{} in retrieval class was expected to return {}'.format(key, val))
        with self.subTest(operation='check output files exist'):
            self.assertTrue(os.path.exists(mwr_file_out), msg='expected MWR file for TROPoe run has not been generated')
            self.assertTrue(os.path.exists(alc_file_out), msg='expected ALC file for TROPoe run has not been generated')

    def test_prepare_model(self):
        self.ret.model_fc_file = None
        self.ret.model_zg_file = None


if __name__ == '__main__':
    unittest.main()