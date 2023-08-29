import unittest

import numpy as np

from mwr_l12l2.errors import MWRFileError
from mwr_l12l2.utils.file_utils import concat_filename, datetime64_from_filename


class TestFileUtils(unittest.TestCase):
    def test_concat_filename(self):
        """Test for concat_filename function"""
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610'), 'L2_0-20000-0-06610.nc')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', ext='.grb'), 'L2_0-20000-0-06610.grb')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', 'A'), 'L2_0-20000-0-06610_A.nc')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', suffix='*', ext=''), 'L2_0-20000-0-06610*')

    def test_datetime64_from_filename(self):
        """""Test for datetime64_from_filename and datestr_from_filename functions"""
        self.assertEqual(datetime64_from_filename('L2_0-20000-0-06610_A_20230828_20311201.nc'),
                         np.datetime64('2031-12-01'))
        self.assertEqual(datetime64_from_filename('L2_0-20000-0-06610_A_202308281559_20311201.nc', '20311201'),
                         np.datetime64('2023-08-28 15:59'))
        with self.assertRaises(MWRFileError):
            datetime64_from_filename('L2_0-20000-0-06610_A.nc')


if __name__ == '__main__':
    unittest.main()
