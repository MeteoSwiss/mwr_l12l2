import os
import shutil
import unittest

import numpy as np
import yaml

from mwr_l12l2.errors import MWRFileError, MWRTestError
from mwr_l12l2.utils.file_utils import abs_file_path, concat_filename, datetime64_from_filename, dict_to_file

dir_out = abs_file_path('tests/data/output_file_utils/')


class TestFileUtils(unittest.TestCase):
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

    def test_concat_filename(self):
        """Test for concat_filename function"""
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610'), 'L2_0-20000-0-06610.nc')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', ext='.grb'), 'L2_0-20000-0-06610.grb')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', 'A'), 'L2_0-20000-0-06610_A.nc')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', suffix='*', ext=''), 'L2_0-20000-0-06610*')

    def test_datetime64_from_filename(self):
        """Test for datetime64_from_filename and datestr_from_filename functions"""
        self.assertEqual(datetime64_from_filename('L2_0-20000-0-06610_A_20230828_20311201.nc'),
                         np.datetime64('2031-12-01'))
        self.assertEqual(datetime64_from_filename('L2_0-20000-0-06610_A_202308281559_20311201.nc', '20311201'),
                         np.datetime64('2023-08-28 15:59'))
        with self.assertRaises(MWRFileError):
            datetime64_from_filename('L2_0-20000-0-06610_A.nc')

    def test_dict_to_file(self):
        """Test for dict_to_file function. Also check that contents remain intact even if specifying header"""
        data = {'key1': 'val1', 'key2': 'val2'}
        file = os.path.join(dir_out, 'test.yaml')

        # write in yaml-like format along with a dummy header as comment (with heading '#')
        dict_to_file(data, file, ': ', '# this is just a test file')

        # reload with PyYAML and verify dict is identical to input
        with open(file) as f:
            dict_loaded = yaml.load(f, Loader=yaml.FullLoader)
            self.assertEqual(data, dict_loaded)


if __name__ == '__main__':
    unittest.main()
