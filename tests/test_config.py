import os
import shutil
import unittest

import yaml

from mwr_l12l2.errors import MWRConfigError, MWRTestError
from mwr_l12l2.utils.config_utils import get_retrieval_config, get_mars_config
from mwr_l12l2.utils.file_utils import abs_file_path

dir_config_orig = abs_file_path('mwr_l12l2/config/')
dir_config_test = abs_file_path('tests/config_testfiles/')

file_ret_orig = os.path.join(dir_config_orig, 'retrieval_config.yaml')
file_ret_test = os.path.join(dir_config_test, 'retrieval_config.yaml')
file_ret_mocked = os.path.join(dir_config_test, 'retrieval_config_mocked.yaml')
file_mars_orig = os.path.join(dir_config_orig, 'mars_config_fc.yaml')
file_mars_test = os.path.join(dir_config_test, 'mars_config_fc.yaml')
file_mars_mocked = os.path.join(dir_config_test, 'mars_config_fc_mocked.yaml')


class TestConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """copy example files to the test config directory

        By doing this here, one would find out for permission issues right at set up instead of causing a failed test.
        """
        if os.path.exists(dir_config_test):
            err_msg = ("directory '{}' is supposed to be created during run of config tests, but should not be there"
                       " when '{}' starts. Please remove it manually (making sure that you don't erase data you might"
                       " still need) and run tests again".format(dir_config_test, __file__))
            raise MWRTestError(err_msg)
        os.mkdir(dir_config_test)

        shutil.copyfile(file_ret_orig, file_ret_test)
        shutil.copyfile(file_mars_orig, file_mars_test)

    @classmethod
    def tearDownClass(cls):
        """remove test config directory again"""
        shutil.rmtree(dir_config_test)

    def test_retrieval_config(self):
        """Test retrieval config file reader and example file in repo"""
        with self.subTest(operation='run on example config file'):
            """test that example config file given in repo processes ok"""
            get_retrieval_config(file_ret_test)
        with self.subTest(operation='test missing keys'):
            """test that an exception is raised if a mandatory key is missing"""
            mandatory_key = 'data'
            remove_var_from_yaml(file_ret_test, file_ret_mocked, mandatory_key)
            with self.assertRaises(MWRConfigError):
                get_retrieval_config(file_ret_mocked)
        with self.subTest(operation='test missing keys in data section'):
            """test that an exception is raised if a mandatory key in subsection is missing"""
            data_key = 'data'
            mandatory_key = 'mwr_dir'
            remove_var_from_yaml(file_ret_test, file_ret_mocked, mandatory_key, data_key)
            with self.assertRaises(MWRConfigError):
                get_retrieval_config(file_ret_mocked)

    def test_mars_config(self):
        """Test mars config file reader and example file in repo"""
        with self.subTest(operation='run on example config file'):
            """test that example config file given in repo processes ok"""
            get_mars_config(file_mars_test)
        with self.subTest(operation='test missing keys'):
            """test that an exception is raised if a mandatory key is missing"""
            mandatory_key = 'request'
            remove_var_from_yaml(file_mars_test, file_mars_mocked, mandatory_key)
            with self.assertRaises(MWRConfigError):
                get_mars_config(file_mars_mocked)
        with self.subTest(operation='test missing keys in request section'):
            """test that an exception is raised if a mandatory key in subsection is missing"""
            data_key = 'request'
            mandatory_key = 'param'
            remove_var_from_yaml(file_mars_test, file_mars_mocked, mandatory_key, data_key)
            with self.assertRaises(MWRConfigError):
                get_mars_config(file_mars_mocked)


def remove_var_from_yaml(file_in, file_out, var, sect=None):
    # read from input file
    with open(file_in) as f:
        conf = yaml.load(f, Loader=yaml.FullLoader)

    # remove variable
    if sect is None:
        del conf[var]
    else:
        del conf[sect][var]

    # write to output file
    with open(file_out, 'w') as f:
        yaml.dump(conf, f)


if __name__ == '__main__':
    unittest.main()
