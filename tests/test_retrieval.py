import glob
import os.path
import shutil
import unittest

import datetime as dt
import numpy as np

from mwr_l12l2.errors import MWRTestError
from mwr_l12l2.retrieval.retrieval import Retrieval
from mwr_l12l2.utils.file_utils import abs_file_path


mwr_dir = abs_file_path('tests/data/mwr/')
mwr_basename = 'MWR_1C01_0-20000-0-10393_A'
mwr_ext = '.nc'
alc_dir = abs_file_path('tests/data/alc/')
alc_basename = 'L2_0-20000-0-10393_0'
alc_ext = '.nc'
model_fc_file = abs_file_path('tests/data/ecmwf_fc/ecmwf_fc_0-20000-0-10393_A_202304250000_converted_to.nc')
model_zg_file = abs_file_path('tests/data/ecmwf_fc/ecmwf_z_0-20000-0-10393_A.grb')
model_get_time = np.datetime64('2023-04-25 14:30:00')

dir_out = abs_file_path('tests/data/output/')
mwr_file_out = os.path.join(dir_out, 'mwr.nc')
alc_file_out = os.path.join(dir_out, 'alc.nc')
model_prof_file_out = os.path.join(dir_out, 'model_prof.nc')
model_sfc_file_out = os.path.join(dir_out, 'model_sfc.nc')


class TestRetrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare test output directory

        Clean up any existing output directory from previous test runs and create a fresh one.
        """
        if os.path.exists(dir_out):
            shutil.rmtree(dir_out)
        os.mkdir(dir_out)

    @classmethod
    def tearDownClass(cls):
        """remove test config directory again"""
        shutil.rmtree(dir_out)

    def setUp(self):
        """initialize a new instance of Retrieval class for each test"""
        self.ret = Retrieval(abs_file_path('mwr_l12l2/config/retrieval_config.yaml'))

    def test_prepare_obs(self):
        """test the preparation of observation files for TROPoe (MWR and ALC)"""
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
            """run prepare_obs method"""
            self.ret.select_instrument()
            self.ret.prepare_obs()
        with self.subTest(operation='check data times'):
            """check that data times inferred by prepare_obs correspond to what is expected from input files"""
            self.assertTrue(np.abs(self.ret.time_mean - expected_mean_time) < np.timedelta64(10, 'm'),
                            msg='mean time inferred from MWR data is not as expected')
        with self.subTest(operation='check vars/files existence status'):
            """check that data data existence inferred by prepare_obs correspond to what is expected from input files"""
            self.assertEqual(self.ret.alc_exists, expected_alc_file_existence,
                             msg='ALC data existence is expected to be {} but retrieval class says {}'.format(
                                 expected_alc_file_existence, self.ret.alc_exists))
            for key, val in expected_mwr_met_existence.items():
                self.assertEqual(getattr(self.ret, key), val,
                                 msg='{} in retrieval class was expected to return {}'.format(key, val))
        with self.subTest(operation='check output files exist'):
            """check that MWR and ALC files for TROPoe have been generated"""
            self.assertTrue(os.path.exists(mwr_file_out), msg='expected MWR file for TROPoe run has not been generated')
            self.assertTrue(os.path.exists(alc_file_out), msg='expected ALC file for TROPoe run has not been generated')

    def test_prepare_obs_single_mwr(self):
        """test the preparation of observation files for TROPoe with one single MWR file present"""
        self.ret.mwr_files = [os.path.join(mwr_dir, mwr_basename + '202304251300' + mwr_ext),]
        expected_mean_time = np.datetime64('2023-04-25 13:30:00')
        expected_mwr_met_existence = {'sfc_temp_obs_exists': True, 'sfc_p_obs_exists': True, 'sfc_rh_obs_exists': False}
        self.ret.alc_files = [os.path.join(alc_dir, alc_basename + '20230425' + alc_ext)]
        expected_alc_file_existence = True
        self.ret.mwr_file_tropoe = mwr_file_out
        self.ret.alc_file_tropoe = alc_file_out

        with self.subTest(operation='run main'):
            """run prepare_obs method"""
            self.ret.select_instrument()
            self.ret.prepare_obs()
        with self.subTest(operation='check data times'):
            """check that data times inferred by prepare_obs correspond to what is expected from input files"""
            self.assertTrue(np.abs(self.ret.time_mean - expected_mean_time) < np.timedelta64(10, 'm'),
                            msg='mean time inferred from MWR data is not as expected')
        with self.subTest(operation='check vars/files existence status'):
            """check that data data existence inferred by prepare_obs correspond to what is expected from input files"""
            self.assertEqual(self.ret.alc_exists, expected_alc_file_existence,
                             msg='ALC data existence is expected to be {} but retrieval class says {}'.format(
                                 expected_alc_file_existence, self.ret.alc_exists))
            for key, val in expected_mwr_met_existence.items():
                self.assertEqual(getattr(self.ret, key), val,
                                 msg='{} in retrieval class was expected to return {}'.format(key, val))
        with self.subTest(operation='check output files exist'):
            """check that MWR and ALC files for TROPoe have been generated"""
            self.assertTrue(os.path.exists(mwr_file_out), msg='expected MWR file for TROPoe run has not been generated')
            self.assertTrue(os.path.exists(alc_file_out), msg='expected ALC file for TROPoe run has not been generated')

    def test_prepare_obs_no_alc(self):
        """test the preparation of observation files for TROPoe with no ALC present (no need to redo all subtests)"""
        self.ret.mwr_files = [os.path.join(mwr_dir, mwr_basename + '202304251300' + mwr_ext),
                              os.path.join(mwr_dir, mwr_basename + '202304251400' + mwr_ext),
                              os.path.join(mwr_dir, mwr_basename + '202304251500' + mwr_ext)]
        self.ret.alc_files = []
        expected_alc_file_existence = False
        self.ret.mwr_file_tropoe = mwr_file_out
        self.ret.alc_file_tropoe = alc_file_out

        with self.subTest(operation='run main'):
            """run prepare_obs method"""
            self.ret.select_instrument()
            self.ret.prepare_obs()
        with self.subTest(operation='check vars/files existence status'):
            """check that data data existence inferred by prepare_obs correspond to what is expected from input files"""
            self.assertEqual(self.ret.alc_exists, expected_alc_file_existence,
                             msg='ALC data existence is expected to be {} but retrieval class says {}'.format(
                                 expected_alc_file_existence, self.ret.alc_exists))
        with self.subTest(operation='check output files exist'):
            """check that MWR file for TROPoe has been generated"""
            self.assertTrue(os.path.exists(mwr_file_out), msg='expected MWR file for TROPoe run has not been generated')

    def test_prepare_model(self):
        """test the preparation of model data for TROPoe"""
        # self.time_min = dt.datetime(2023, 4, 25, 0, 0, 0)
        # self.time_max = dt.datetime(2023, 4, 25, 23, 0, 0)
        self.ret.sfc_temp_obs_exists = False
        self.ret.sfc_rh_obs_exists = False
        self.ret.sfc_p_obs_exists = False
        self.ret.model_fc_file = model_fc_file
        self.ret.model_zg_file = model_zg_file
        self.ret.model_prof_file_tropoe = model_prof_file_out
        self.ret.model_sfc_file_tropoe = model_sfc_file_out

        self.ret.time_min = model_get_time
        self.ret.time_max = model_get_time

        with self.subTest(operation='run main'):
            """run prepare_model method"""
            self.ret.select_instrument()
            self.ret.prepare_model()
        with self.subTest(operation='check output files exist'):
            """check that model profiles and surface files for TROPoe have been generated"""
            self.assertTrue(os.path.exists(model_prof_file_out),
                            msg='expected model profile data file for TROPoe run has not been generated')
            self.assertTrue(os.path.exists(model_sfc_file_out),
                            msg='expected moddel surface data file for TROPoe run has not been generated')

    def test_run_retrieval(self):
        """test the full retrieval workflow from start to finish (integration test)"""
        expected_start_time = dt.datetime(2023, 4, 25, 13, 0, 0)
        expected_end_time = dt.datetime(2023, 4, 25, 13, 15, 0)

        # Override output directory to use test output directory
        self.ret.conf['data']['output_dir'] = dir_out

        with self.subTest(operation='run main'):
            """run the full retrieval workflow"""
            self.ret.run(start_time=expected_start_time, end_time=expected_end_time)
        
        with self.subTest(operation='check L2 output file exists'):
            """check that MWR L2 file has been successfully created in output directory"""
            # With these time provided, the expected L2 file name is as follows:
            L2_filename = 'MWR_2C01_0-20000-0-10393_A202304251315.nc'
            
            self.assertTrue(os.path.exists(os.path.join(dir_out, L2_filename)),
                           msg='No MWR L2 file was generated in {} matching pattern {}'.format(
                               dir_out, L2_filename))

            # Check that at least one file exists and has reasonable size
            self.assertTrue(os.path.exists(os.path.join(dir_out, L2_filename)),
                            msg='Expected L2 file {} does not exist'.format(L2_filename))
            file_size = os.path.getsize(os.path.join(dir_out, L2_filename))
            self.assertGreater(file_size, 0,
                              msg='L2 file {} exists but is empty'.format(L2_filename))


if __name__ == '__main__':
    unittest.main()