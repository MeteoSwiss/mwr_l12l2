import os
import shutil
import unittest
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import datetime as dt
import pandas as pd
import numpy as np

from mwr_l12l2.errors import MWRConfigError, MissingDataError
from mwr_l12l2.retrieval.monitoring import Level1Monitoring
from mwr_l12l2.utils.file_utils import abs_file_path


class TestLevel1Monitoring(unittest.TestCase):
    """Test the Level1Monitoring class"""
    
    def setUp(self):
        """Set up test fixtures before each test method"""
        # Create a temporary directory for test outputs
        self.test_dir = tempfile.mkdtemp()
        
        # Mock configuration dictionary
        self.mock_config = {
            'data': {
                'mwr_dir': os.path.join(self.test_dir, 'mwr'),
                'alc_dir': os.path.join(self.test_dir, 'alc'), 
                'mwr_file_prefix': 'MWR_1C01_',
                'alc_file_prefix': 'L2_',
                'inst_config_dir': os.path.join(self.test_dir, 'inst_config'),
                'inst_config_file_prefix': 'inst_'
            }
        }
        
        # Create mock directories
        os.makedirs(self.mock_config['data']['mwr_dir'])
        os.makedirs(self.mock_config['data']['alc_dir'])
        os.makedirs(self.mock_config['data']['inst_config_dir'])
        
        # Create mock instrument list
        self.mock_instrument_df = pd.DataFrame({
            'wigos_station_id': ['0-20000-0-12345', '0-20000-0-67890'],
            'instrument_id': ['A', 'B'],
            'station_name': ['Test Station 1', 'Test Station 2']
        })

    def tearDown(self):
        """Clean up after each test"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    def test_init_with_dict_config(self, mock_read_csv):
        """Test initialization with dictionary configuration"""
        mock_read_csv.return_value = self.mock_instrument_df
        
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        
        self.assertEqual(monitor.conf, self.mock_config)
        self.assertTrue(isinstance(monitor.l1_instrument_list, pd.DataFrame))
        mock_read_csv.assert_called_once_with('test_instrument_list.csv')

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('mwr_l12l2.retrieval.monitoring.get_retrieval_config')
    def test_init_with_file_config(self, mock_get_config, mock_read_csv):
        """Test initialization with file path configuration"""
        config_file = os.path.join(self.test_dir, 'config.yaml')
        with open(config_file, 'w') as f:
            f.write("dummy config")
            
        mock_get_config.return_value = self.mock_config
        mock_read_csv.return_value = self.mock_instrument_df
        
        monitor = Level1Monitoring(config_file, 'test_instrument_list.csv')
        
        mock_get_config.assert_called_once_with(config_file)
        self.assertEqual(monitor.conf, self.mock_config)

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    def test_init_with_invalid_config(self, mock_read_csv):
        """Test initialization with invalid configuration"""
        mock_read_csv.return_value = self.mock_instrument_df
        
        with self.assertRaises(MWRConfigError):
            Level1Monitoring('nonexistent_config.yaml', 'test_instrument_list.csv')

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('mwr_l12l2.retrieval.monitoring.get_inst_config')
    @patch('glob.glob')
    def test_set_instrument_success(self, mock_glob, mock_get_inst_config, mock_read_csv):
        """Test successful instrument setting"""
        mock_read_csv.return_value = self.mock_instrument_df
        mock_glob.return_value = ['test_file.nc']
        mock_inst_config = {'dummy': 'config'}
        mock_get_inst_config.return_value = mock_inst_config
        
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        monitor.set_instrument('0-20000-0-12345', 'A')
        
        self.assertEqual(monitor.wigos, '0-20000-0-12345')
        self.assertEqual(monitor.inst_id, 'A')
        self.assertEqual(monitor.inst_conf, mock_inst_config)

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('mwr_l12l2.retrieval.monitoring.get_inst_config')
    @patch('glob.glob')
    def test_set_instrument_no_files(self, mock_glob, mock_get_inst_config, mock_read_csv):
        """Test instrument setting when no MWR files exist"""
        mock_read_csv.return_value = self.mock_instrument_df
        mock_glob.return_value = []  # No files found
        mock_get_inst_config.return_value = {'test': 'config'}  # Mock config
        
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        
        # Should not raise an exception but log an error
        monitor.set_instrument('0-20000-0-12345', 'A')
        self.assertEqual(monitor.wigos, '0-20000-0-12345')
        self.assertEqual(monitor.inst_id, 'A')

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('glob.glob')
    def test_list_obs_files(self, mock_glob, mock_read_csv):
        """Test listing observation files"""
        mock_read_csv.return_value = self.mock_instrument_df
        mock_mwr_files = ['mwr_file1.nc', 'mwr_file2.nc']
        mock_alc_files = ['alc_file1.nc']
        
        # Configure glob to return different files based on pattern
        def glob_side_effect(pattern):
            if 'MWR_1C01_' in pattern:
                return mock_mwr_files
            elif 'L2_' in pattern:
                return mock_alc_files
            return []
        
        mock_glob.side_effect = glob_side_effect
        
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        monitor.wigos = '0-20000-0-12345'
        monitor.inst_id = 'A'
        
        monitor.list_obs_files()
        
        self.assertEqual(monitor.mwr_files, mock_mwr_files)
        self.assertEqual(monitor.alc_files, mock_alc_files)

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('glob.glob')
    def test_list_obs_files_no_mwr(self, mock_glob, mock_read_csv):
        """Test listing observation files when no MWR files exist"""
        mock_read_csv.return_value = self.mock_instrument_df
        
        def glob_side_effect(pattern):
            if 'MWR_1C01_' in pattern:
                return []  # No MWR files
            elif 'L2_' in pattern:
                return ['alc_file1.nc']
            return []
        
        mock_glob.side_effect = glob_side_effect
        
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        monitor.wigos = '0-20000-0-12345'
        monitor.inst_id = 'A'
        
        # This should log a critical error but not raise an exception
        monitor.list_obs_files()
        self.assertEqual(monitor.mwr_files, [])

class TestComputeOmBMethod(unittest.TestCase):
    """Test the compute_OmB_for_single_instrument method"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp()
        
        # Mock configuration dictionary
        self.mock_config = {
            'data': {
                'mwr_dir': os.path.join(self.test_dir, 'mwr'),
                'alc_dir': os.path.join(self.test_dir, 'alc'), 
                'mwr_file_prefix': 'MWR_1C01_',
                'alc_file_prefix': 'L2_',
                'inst_config_dir': os.path.join(self.test_dir, 'inst_config'),
                'inst_config_file_prefix': 'inst_'
            },
            'quicklook_outdir': os.path.join(self.test_dir, 'quicklooks')
        }
        
        # Create mock directories
        os.makedirs(self.mock_config['data']['mwr_dir'])
        os.makedirs(self.mock_config['data']['alc_dir'])
        os.makedirs(self.mock_config['data']['inst_config_dir'])
        os.makedirs(self.mock_config['quicklook_outdir'])
        
    def tearDown(self):
        """Clean up after each test"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('mwr_l12l2.retrieval.monitoring.Retrieval')
    @patch('mwr_l12l2.retrieval.monitoring.ObservationMinusBackground')
    @patch('mwr_l12l2.retrieval.monitoring.get_inst_config')
    @patch('glob.glob')
    def test_compute_omb_with_files(self, mock_glob, mock_get_inst_config,
                                     mock_omb, mock_retrieval, mock_read_csv):
        """Test compute_OmB_for_single_instrument method with files"""
        mock_instrument_df = pd.DataFrame({
            'wigos_station_id': ['0-20000-0-12345'],
            'instrument_id': ['A']
        })
        mock_read_csv.return_value = mock_instrument_df
        
        # Mock file listings
        def glob_side_effect(pattern):
            if 'MWR_1C01_' in pattern:
                return ['test_file.nc']
            elif 'L2_' in pattern:
                return ['alc_file.nc']
            return []
        mock_glob.side_effect = glob_side_effect
        
        # Mock instrument config
        mock_get_inst_config.return_value = {'test': 'config'}
        
        # Mock the Retrieval instance
        mock_ret = Mock()
        mock_ret.tropoe_omb_file = 'test_omb.nc'
        mock_retrieval.return_value = mock_ret
        
        # Mock ObservationMinusBackground
        mock_omb_instance = Mock()
        mock_omb.return_value = mock_omb_instance
        
        # Create the monitor instance and run
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        start_time = dt.datetime(2023, 4, 24)
        end_time = dt.datetime(2023, 4, 25)
        
        monitor.compute_OmB_for_single_instrument('0-20000-0-12345', 'A', start_time, end_time)
        
        # Verify that Retrieval was instantiated with OmB=True
        mock_retrieval.assert_called_once()
        mock_ret.monitor.assert_called_once_with(start_time, end_time, OmB=True)
        
        # Verify OmB processing was called
        mock_omb_instance.read_tropoe.assert_called_once()
        mock_omb_instance.plot_omb.assert_called_once()

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('mwr_l12l2.retrieval.monitoring.get_inst_config')
    @patch('glob.glob')
    def test_compute_omb_no_files(self, mock_glob, mock_get_inst_config, mock_read_csv):
        """Test compute_OmB_for_single_instrument when no MWR files exist"""
        mock_instrument_df = pd.DataFrame({
            'wigos_station_id': ['0-20000-0-12345'],
            'instrument_id': ['A']
        })
        mock_read_csv.return_value = mock_instrument_df
        mock_glob.return_value = []  # No files found
        mock_get_inst_config.return_value = {'test': 'config'}  # Mock config
        
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        start_time = dt.datetime(2023, 4, 24)
        end_time = dt.datetime(2023, 4, 25)
        
        # Should not raise an exception but should skip processing
        monitor.compute_OmB_for_single_instrument('0-20000-0-12345', 'A', start_time, end_time)


class TestMonitorMwrL1Method(unittest.TestCase):
    """Test the monitor_mwr_l1 method of Level1Monitoring class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp()
        self.test_day = dt.datetime(2023, 4, 25)
        
        # Mock configuration dictionary with quicklook_outdir
        self.mock_config = {
            'data': {
                'mwr_dir': os.path.join(self.test_dir, 'mwr'),
                'alc_dir': os.path.join(self.test_dir, 'alc'), 
                'mwr_file_prefix': 'MWR_1C01_',
                'alc_file_prefix': 'L2_',
                'inst_config_dir': os.path.join(self.test_dir, 'inst_config'),
                'inst_config_file_prefix': 'inst_'
            },
            'quicklook_outdir': os.path.join(self.test_dir, 'quicklooks')
        }
        
        # Create mock directories
        os.makedirs(self.mock_config['data']['mwr_dir'])
        os.makedirs(self.mock_config['data']['alc_dir'])
        os.makedirs(self.mock_config['data']['inst_config_dir'])
        os.makedirs(self.mock_config['quicklook_outdir'])
        
    def tearDown(self):
        """Clean up after each test"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        
    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('mwr_l12l2.retrieval.monitoring.get_inst_config')
    @patch('matplotlib.pyplot.close')
    @patch('glob.glob')
    def test_monitor_mwr_l1_no_files(self, mock_glob, mock_close, mock_get_inst_config, mock_read_csv):
        """Test monitor_mwr_l1 method when no MWR files are found"""
        # Mock the instrument list
        mock_instrument_df = pd.DataFrame({
            'wigos_station_id': ['0-20000-0-12345'],
            'instrument_id': ['A']
        })
        mock_read_csv.return_value = mock_instrument_df
        
        # Mock glob and inst_config
        def glob_side_effect(pattern):
            if 'MWR_1C01_' in pattern:
                return []  # No MWR files at first
            return []
        mock_glob.side_effect = glob_side_effect
        mock_get_inst_config.return_value = {'test': 'config'}
        
        # Create the monitor instance
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        
        # Run the method
        monitor.monitor_mwr_l1(day=self.test_day)
        
        # Verify that plt.close was called (indicates a figure was created and closed)
        mock_close.assert_called_once()
        
        # Verify that an image file was created
        expected_file = os.path.join(self.mock_config['quicklook_outdir'], 
                                     'L1_0-20000-0-12345_A_20230424_zenith.jpg')
        self.assertTrue(os.path.exists(expected_file))

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('mwr_l12l2.retrieval.monitoring.Retrieval')
    @patch('mwr_l12l2.retrieval.monitoring.Level1')
    @patch('mwr_l12l2.retrieval.monitoring.ObservationMinusBackground')
    @patch('mwr_l12l2.retrieval.monitoring.get_inst_config')
    @patch('glob.glob')
    def test_monitor_mwr_l1_with_files(self, mock_glob, mock_get_inst_config, 
                                       mock_omb, mock_level1, mock_retrieval, mock_read_csv):
        """Test monitor_mwr_l1 method when MWR files are found"""
        # Mock the instrument list
        mock_instrument_df = pd.DataFrame({
            'wigos_station_id': ['0-20000-0-12345'],
            'instrument_id': ['A']
        })
        mock_read_csv.return_value = mock_instrument_df
        
        # Mock file listings
        def glob_side_effect(pattern):
            if 'MWR_1C01_' in pattern:
                return ['test_file.nc']
            elif 'L2_' in pattern:
                return ['alc_file.nc']
            return []
        mock_glob.side_effect = glob_side_effect
        
        # Mock instrument config
        mock_get_inst_config.return_value = {'test': 'config'}
        
        # Mock the Retrieval instance
        mock_ret = Mock()
        mock_ret.tropoe_omb_file = 'test_omb.nc'
        mock_ret.mwr = Mock()
        mock_retrieval.return_value = mock_ret
        
        # Mock Level1 and ObservationMinusBackground
        mock_quicklook = Mock()
        mock_level1.return_value = mock_quicklook
        mock_omb_instance = Mock()
        mock_omb.return_value = mock_omb_instance
        
        # Create the monitor instance and run
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        monitor.monitor_mwr_l1(day=self.test_day)
        
        # Verify that Retrieval was instantiated and monitor was called
        mock_retrieval.assert_called_once()
        mock_ret.monitor.assert_called_once()
        
        # Verify the arguments passed to Retrieval
        args, kwargs = mock_retrieval.call_args
        self.assertEqual(args[0], self.mock_config)
        self.assertEqual(kwargs['node'], 1)
        
        # Check the selected_instrument dictionary structure
        selected_instrument = args[1]
        expected_keys = ['wigos', 'inst_id', 'inst_conf', 'mwr_files', 'alc_files']
        self.assertTrue(all(key in selected_instrument for key in expected_keys))
        
        # Verify Level1 and OmB plotting were called
        mock_quicklook.plot_l1.assert_called_once()
        mock_omb_instance.read_tropoe.assert_called_once()
        mock_omb_instance.plot_omb.assert_called_once()

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('glob.glob')
    def test_monitor_mwr_l1_exception_handling(self, mock_glob, mock_read_csv):
        """Test monitor_mwr_l1 method exception handling"""
        # Mock the instrument list
        mock_instrument_df = pd.DataFrame({
            'wigos_station_id': ['0-20000-0-12345'],
            'instrument_id': ['A']
        })
        mock_read_csv.return_value = mock_instrument_df
        
        # Configure glob to raise an exception
        mock_glob.side_effect = Exception("Test exception")
        
        # Create the monitor instance
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        
        # This should not raise an exception due to try/except handling
        try:
            monitor.monitor_mwr_l1(day=self.test_day)
        except Exception:
            self.fail("monitor_mwr_l1 should handle exceptions gracefully")

    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    @patch('mwr_l12l2.retrieval.monitoring.Retrieval')
    @patch('mwr_l12l2.retrieval.monitoring.Level1')
    @patch('mwr_l12l2.retrieval.monitoring.ObservationMinusBackground')
    @patch('mwr_l12l2.retrieval.monitoring.get_inst_config')
    @patch('glob.glob')
    def test_monitor_mwr_l1_multiple_instruments(self, mock_glob, mock_get_inst_config,
                                                 mock_omb, mock_level1, mock_retrieval, mock_read_csv):
        """Test monitor_mwr_l1 method with multiple instruments"""
        # Mock the instrument list with multiple instruments
        mock_instrument_df = pd.DataFrame({
            'wigos_station_id': ['0-20000-0-12345', '0-20000-0-67890'],
            'instrument_id': ['A', 'B']
        })
        mock_read_csv.return_value = mock_instrument_df
        
        # Mock file listings
        def glob_side_effect(pattern):
            if 'MWR_1C01_' in pattern:
                return ['test_file.nc']
            elif 'L2_' in pattern:
                return ['alc_file.nc']
            return []
        mock_glob.side_effect = glob_side_effect
        
        # Mock instrument config
        mock_get_inst_config.return_value = {'test': 'config'}
        
        # Mock the Retrieval instance
        mock_ret = Mock()
        mock_ret.tropoe_omb_file = 'test_omb.nc'
        mock_ret.mwr = Mock()
        mock_retrieval.return_value = mock_ret
        
        # Mock Level1 and ObservationMinusBackground
        mock_quicklook = Mock()
        mock_level1.return_value = mock_quicklook
        mock_omb_instance = Mock()
        mock_omb.return_value = mock_omb_instance
        
        # Create the monitor instance and run
        monitor = Level1Monitoring(self.mock_config, 'test_instrument_list.csv')
        monitor.monitor_mwr_l1(day=self.test_day)
        
        # Verify that Retrieval was called twice (once for each instrument)
        self.assertEqual(mock_retrieval.call_count, 2)
        self.assertEqual(mock_ret.monitor.call_count, 2)


class TestMonitoringUtilsIntegration(unittest.TestCase):
    """Integration tests for monitoring utilities"""
    
    @patch('mwr_l12l2.retrieval.monitoring.read_mwr_summary_csv')
    def test_read_csv_integration(self, mock_read_csv):
        """Test integration with CSV reading functionality"""
        mock_df = pd.DataFrame({
            'wigos_station_id': ['0-20000-0-12345'],
            'instrument_id': ['A'],
            'station_name': ['Test Station']
        })
        mock_read_csv.return_value = mock_df
        
        config = {'data': {'mwr_dir': '/tmp'}}
        monitor = Level1Monitoring(config, 'test.csv')
        
        self.assertIsInstance(monitor.l1_instrument_list, pd.DataFrame)
        self.assertEqual(len(monitor.l1_instrument_list), 1)
        mock_read_csv.assert_called_once_with('test.csv')


if __name__ == '__main__':
    # Create test suite using TestLoader (modern approach)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestLevel1Monitoring))
    suite.addTests(loader.loadTestsFromTestCase(TestComputeOmBMethod))
    suite.addTests(loader.loadTestsFromTestCase(TestMonitorMwrL1Method))
    suite.addTests(loader.loadTestsFromTestCase(TestMonitoringUtilsIntegration))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with error code if tests failed
    exit(0 if result.wasSuccessful() else 1)