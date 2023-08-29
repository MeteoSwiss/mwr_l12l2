import unittest

from mwr_l12l2.utils.file_utils import concat_filename, datetime64_from_filename


class TestFileUtils(unittest.TestCase):
    def test_concat_filename(self):
        """Test for concat_filename function"""
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610'), 'L2_0-20000-0-06610.nc')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', ext='.grb'), 'L2_0-20000-0-06610.grb')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', 'A'), 'L2_0-20000-0-06610_A.nc')
        self.assertEqual(concat_filename('L2_', '0-20000-0-06610', suffix='*', ext=''), 'L2_0-20000-0-06610*')


if __name__ == '__main__':
    unittest.main()
