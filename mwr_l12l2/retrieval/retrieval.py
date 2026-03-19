import glob
import os
import shutil
import boto3

import datetime as dt
import numpy as np
import pytz
import xarray as xr

from mwr_l12l2.errors import MissingDataError, MWRConfigError, MWRInputError, MWRRetrievalError
from mwr_l12l2.log import logger
from mwr_l12l2.model.ecmwf.interpret_ecmwf import ModelInterpreter
from mwr_l12l2.retrieval.tropoe_helpers import (model_to_tropoe, run_tropoe, 
                                                  build_vip_config, write_vip_file, convert_tropoe_output)
from mwr_l12l2.utils.config_utils import get_retrieval_config, get_inst_config, get_nc_format_config, get_conf
from mwr_l12l2.utils.data_utils import datetime64_to_str, get_from_nc_files, has_data, datetime64_to_hour, \
    scalars_to_time, vectors_to_time
from mwr_l12l2.utils.file_utils import abs_file_path, concat_filename, datetime64_from_filename, dict_to_file, \
    generate_output_filename
from mwr_l12l2.utils.atmosphere_utils import calculate_pressure_from_std_atmosphere, calculate_derived_product
from mwr_l12l2.write_netcdf import Writer


class Retrieval:
    """Class for gathering and preparing all necessary information to run the retrieval

    Args:
        conf: configuration file or dictionary
        node: identifier for different parallel TROPoe runs. Defaults to 0.
    """

    def __init__(self, conf, selected_instrument=None, node=0):
        if isinstance(conf, dict):
            self.conf = conf
        elif os.path.isfile(conf):
            self.conf = get_retrieval_config(conf)
        else:
            logger.error("The argument 'conf' must be a conf dictionary or a path pointing to a config file")
            raise MWRConfigError("The argument 'conf' must be a conf dictionary or a path pointing to a config file")

        # If provided, we read here the instrument configuation
        if selected_instrument is not None:
            self.wigos = selected_instrument['wigos']
            self.inst_id = selected_instrument['inst_id']
            self.inst_conf = selected_instrument['inst_conf']    
            self.mwr_files = selected_instrument['mwr_files']
            self.alc_files = selected_instrument['alc_files']
            self.tropoe_output_basename = self.conf['data']['result_basefilename_tropoe'] + '_' + self.wigos + self.inst_id
        else:
            # set by select_instrument():
            self.wigos = None
            self.inst_id = None
            self.inst_conf = None
            self.tropoe_output_basename = None

            # set by list_obs():
            self.mwr_files = None
            self.alc_files = None
        
        self.node = node

        # set by prepare_pahts():
        self.tropoe_dir = None  # directory to store temporary data and config files for the current run of TROPoe
        self.vip_file_tropoe = None
        self.mwr_file_tropoe = None
        self.alc_file_tropoe = None
        self.model_prof_file_tropoe = None  # extracted model reference profiles and uncertainties (as input to TROPoe)
        self.model_sfc_file_tropoe = None  # output file for inter/extrapolation of model data to station altitude
        self.tropoe_dir_mountpoint = None  # mountpoint for tropoe_dir inside the TROPoe container

        # set by prepare_obs():
        self.mwr = None  # Level1 contents of MWR instrument for considered time period
        self.time_min = None  # min time of MWR observations available and considered
        self.time_max = None  # max time of MWR observations available and considered
        self.time_mean = None  # average time of period containing considered MWR observations
        self.scan_angle_info = None # Information on the 
        self.sfc_temp_obs_exists = None  # is temperature measured by met station of MWR instrument?
        self.sfc_rh_obs_exists = None  # is rel humidity measured by met station of MWR instrument?
        self.sfc_p_obs_exists = None  # is pressure measured by met station of MWR instrument?
        self.alc_exists = None  # is cloud base measured by co-located ceilometer?
        self.station_psfc_min = None  # minimum allowed surface pressure for the station (calculated from altitude and std atmosphere)
        self.station_psfc_max = None  # maximum allowed surface pressure for the station (calculated from altitude and std atmosphere)
        
        # set by choose_mode_files():
        self.model_fc_file = None
        self.model_zg_file = None
        
        # set by prepare_model():
        self.met_sfc_offset = 0 # Default to 0 as TROPoe should then try to use the higher opacity channels to find T. 
        
        # Will be set during processing
        self.use_model_data = False
        self.ext_sfc_data_type = None
        self.station_latitude = None
        self.station_longitude = None
        self.station_altitude = None
        self.station_pressure = None

    # ============================================================================
    # Properties for better readability
    # ============================================================================
    
    @property
    def has_complete_surface_data(self):
        """Check if all required surface measurements exist."""
        return (self.sfc_temp_obs_exists and 
                self.sfc_rh_obs_exists and 
                self.sfc_p_obs_exists)
    
    @property
    def needs_model_data(self):
        """Determine if model data is required for this retrieval."""
        return self._uses_model_as_pseudo_obs() # or not self.has_complete_surface_data 
        # TODO: for now leaving the model out in case of missing surface data as TROPoe can extract it from the MWR observations itself.

    def _uses_model_as_pseudo_obs(self):
        """Check if model data is configured to be used as pseudo observations."""
        return (self.conf['vip']['mod_temp_prof_type'] != 0 or 
                self.conf['vip']['mod_wv_prof_type'] != 0)
    
    def _validate_time_input(self, start_time, end_time):
        """Validate and adjust start_time and end_time parameters.
        
        Args:
            start_time: User-provided start time or None
            end_time: User-provided end time or None
            
        Returns:
            tuple: (validated_start_time, validated_end_time)
            
        Raises:
            MWRInputError: If start_time is not a datetime object or None
        """
        # Validate start_time type
        if start_time is not None and not isinstance(start_time, dt.datetime):
            logger.error("input argument 'start_time' is expected to be of type datetime.datetime or None")
            raise MWRInputError("input argument 'start_time' is expected to be of type datetime.datetime or None")
        
        # Make sure that the provided start_time is timezone-aware in UTC
        if start_time is not None and start_time.tzinfo is None:
            logger.info('Assuming provided start_time is in UTC timezone')
            start_time = start_time.replace(tzinfo=pytz.UTC)        
        
        # Apply default start_time based on max_age if not provided
        if start_time is None and self.conf['data']['max_age'] is not None:
            logger.info('No start time provided. Using data from the last {} minutes.'.format(
                self.conf['data']['max_age']))
            start_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
                minutes=self.conf['data']['max_age'])
        
        # Apply default end_time if not provided
        if end_time is None:
            end_time = dt.datetime.now(dt.timezone.utc)
        else:
            # Make sure that the provided end_time is timezone-aware in UTC
            if end_time.tzinfo is None:
                logger.info('Assuming provided end_time is in UTC timezone')
                end_time = end_time.replace(tzinfo=pytz.UTC)
        
        return start_time, end_time

    # ============================================================================
    # Main workflow methods
    # ============================================================================

    def run(self, start_time=None, end_time=None):
        """run the entire retrieval chain

        Args:
            start_time (optional): earliest time from which to consider data. If not specified, all data younger than
                'max_age' specified in retrieval config will be used or, if 'max_age' is None, age of data is unlimited.
            end_time (optional): latest time from which to consider data. If not specified, all data received by now is
                processed.
        """
        # Validate and adjust time parameters
        start_time, end_time = self._validate_time_input(start_time, end_time)
        # start_time can be left at None to consider earliest available MWR data

        datestamp = start_time.strftime('%Y%m%d')

        self.prepare_paths(datestamp)
        self.prepare_tropoe_dir()

        # Now only new instrument selection if not provided by a RetrievalManager or an InstrumentSelector
        if self.wigos is None:
            logger.info('No instrument specified. Selecting the oldest one.')
            self.select_instrument()

        if self.mwr_files is None:
            self.list_obs_files(start_time=start_time, end_time=end_time)
        self.prepare_obs(start_time=start_time, end_time=end_time,
                         delete_mwr_in=False)  # TODO: switch delete_mwr_in to True for operational processing
        # TODO: Make sure that we have at least 10 minutes of data before running the retrieval and deleting files !
        
        # Determine if model data is needed (as pseudo observations or TODO for missing surface data)
        self.use_model_data = self._uses_model_as_pseudo_obs()
        
        if self.needs_model_data:
            logger.info('Reading model data for this retrieval (as pseudo observations or because no met data exist)')
            try:
                self.choose_model_files()
                self.prepare_model()
            except Exception as e:
                logger.warning(e)
                self.use_model_data = False
                logger.warning('No model data will be used for the retrieval')
            
        self.prepare_vip()
        self.do_retrieval()
        self.postprocess_tropoe()
        # TODO: adapt drawing on https://meteoswiss.atlassian.net/wiki/spaces/MDA/pages/46564537/L2+retrieval+EWC
        #  by inverting order between interpret_ecmwf and prepare_eprofile

    def monitor(self, start_time=None, end_time=None, OmB=False):
        """Only do the monitoring

        Args:
            start_time (optional): earliest time from which to consider data. If not specified, all data younger than
                'max_age' specified in retrieval config will be used or, if 'max_age' is None, age of data is unlimited.
            end_time (optional): latest time from which to consider data. If not specified, all data received by now is
                processed.
            OmB (optional): If True, perform Observation minus Background calculation.
        """
        # Validate and adjust time parameters
        start_time, end_time = self._validate_time_input(start_time, end_time)
        # end_time/start_time can be left at None to consider latest/earliest available MWR data

        datestamp = start_time.strftime('%Y%m%d')

        self.prepare_paths(datestamp)
        self.prepare_tropoe_dir()

        # Now only new instrument selection if not provided by a RetrievalManager or an InstrumentSelector
        if self.wigos is None:
            logger.info('No instrument specified. Selecting the oldest one.')
            self.select_instrument()
            self.list_obs_files()

        self.prepare_obs(start_time=start_time, end_time=end_time,
                         delete_mwr_in=False)  # TODO: switch delete_mwr_in to True for operational processing
        # TODO: Make sure that we have at least 10 minutes of data before running the retrieval and deleting files !
        # only read model data if it's actually required
        
        if OmB:
            try:
                # start the OmB calculation from TROPoe:
                self.use_model_data = True
                vip_edits = dict(omb_flag=1)
                self.conf['vip'].update(vip_edits)          
                
                # Read model data
                logger.info('Reading model data for this OmB calculation')
                try:
                    self.choose_model_files()
                    self.prepare_model(OmB)
                except Exception as e:
                    raise MWRRetrievalError('Cannot perform OmB calculation without model data: {}'.format(e))
                    
                self.prepare_vip()
                #print(self.mwr)       

                self.do_retrieval()
                logger.info('Post-processing TROPoe output for OmB calculation')
                outfiles_pattern = os.path.join(self.tropoe_dir, self.tropoe_output_basename + '*.nc')
                outfiles = glob.glob(outfiles_pattern)
                if len(outfiles) == 1:
                    # Copy the file to the quicklook directory
                    omb_file = os.path.join(self.conf['omb_outdir'], os.path.basename(outfiles[0]))
                    shutil.copy(outfiles[0], omb_file)
                    self.tropoe_omb_file = omb_file
                elif len(outfiles) == 0:
                    raise MWRRetrievalError('Found no file matching {}. Possibly the TROPoe did not run through.'.format(
                        outfiles_pattern))
                elif len(outfiles) > 1:
                    raise MWRRetrievalError("Found several files matching {}. Don't know which TROPoe output to use.".format(
                        outfiles_pattern))
                logger.info('OmB calculation done.')
            except Exception as e:
                logger.error(f'Error during OmB calculation: {e}, SKIPPING OmB calculation.')

    def prepare_paths(self, datestamp='', netcdf_ext='.nc'):
        """prepare input and output paths and filenames from config"""
        self.tropoe_dir = os.path.join(self.conf['data']['tropoe_basedir'],
                                       '{}{}/'.format(self.conf['data']['tropoe_subfolder_basename'], self.node))
        self.vip_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['vip_filename_tropoe'])
        self.mwr_file_tropoe = os.path.join(self.tropoe_dir,
                                            self.conf['data']['mwr_basefilename_tropoe'] + datestamp + netcdf_ext)
        self.alc_file_tropoe = os.path.join(self.tropoe_dir,
                                            self.conf['data']['alc_basefilename_tropoe'] + datestamp + netcdf_ext)
        self.model_prof_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['model_prof_basefilename_tropoe'] + netcdf_ext)
        self.model_sfc_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['model_sfc_basefilename_tropoe']
                                                  + datestamp + netcdf_ext)
        self.tropoe_dir_mountpoint = self.conf['data']['tropoe_dir_mountpoint']

    def prepare_tropoe_dir(self):
        """set up an empty tropoe tmp file directory for the current node (remove old one if existing)"""
        if os.path.exists(self.tropoe_dir):
            shutil.rmtree(self.tropoe_dir)
        os.mkdir(self.tropoe_dir)

    def select_instrument(self):
        """Selects the instrument which has the oldest MWR file in the input directory (based on its filename).

        Note that this method is not called in case of the operationnal processing or in case we already have the WIGOS number setup.

        This method finds the oldest file in the folder and extracts the station ID from the filename or file content.
        It then retrieves the instrument configuration based on the station ID and instrument ID.
        Finally, it sets the necessary attributes for further processing.

        Raises:
            MissingDataError: If no MWR data is found in the specified directory.
        """
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                               '{}*.nc'.format(self.conf['data']['mwr_file_prefix'])))
        
        if not list_of_files:
            logger.error('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
            raise MissingDataError('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
        
        # extract filename and dates of all files
        list_of_file_date = [os.path.basename(x).split('/')[-1].split('_')[3] for x in list_of_files]
        list_of_dates = [dt.datetime.strptime(x[1:-3], '%Y%m%d%H%M%S') for x in list_of_file_date]

        # get oldest file based on the date in the filename:
        id_oldest = list_of_dates.index(min(list_of_dates))
        oldest_file = list_of_files[id_oldest]
        
        # get station id from filename
        self.wigos = oldest_file.split('/')[-1].split('_')[2]
        #self.wigos = '0-20000-0-10505'
        
        self.inst_id = oldest_file.split('/')[-1].split('_')[3][0]
        #self.inst_id = 'A'

        inst_conf_file = '{}{}_{}.yaml'.format(self.conf['data']['inst_config_file_prefix'],
                                               self.wigos, self.inst_id)
        self.inst_conf = get_inst_config(os.path.join(self.conf['data']['inst_config_dir'], inst_conf_file))

        self.tropoe_output_basename = self.conf['data']['result_basefilename_tropoe'] + '_' + self.wigos + self.inst_id

    def list_obs_files(self, start_time=None, end_time=None):
        """get file lists for the selected station

        Note:
             this method shall list all (MWR) files not just the ones matching time settings. Like that old (obsolete)
             files are removed when :meth:`prepare_obs` is run with delete_mwr_in=True
        """
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                                '{}*{}_{}*.nc'.format(self.conf['data']['mwr_file_prefix'],
                                                                      self.wigos, self.inst_id)))
        if not list_of_files:
            logger.error('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
            raise MissingDataError('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
        
        # extract filename and dates of all files
        list_of_file_date = [os.path.basename(x).split('/')[-1].split('_')[3] for x in list_of_files]
        try:
            list_of_dates = [dt.datetime.strptime(x[1:-3], '%Y%m%d%H%M%S').replace(tzinfo=pytz.UTC) for x in list_of_file_date]
        except ValueError as e:
            logger.warning('Non standard filename, trying to use daily concatenated filename instead.')
            list_of_dates = [dt.datetime.strptime(x[1:-3], '%Y%m%d').replace(tzinfo=pytz.UTC) for x in list_of_file_date]
        
        # Now only keep the files within the time range (+ threshold) if provided
        if start_time is not None:
            file_time_threshold = self.conf['data']['file_time_threshold_hours']
            valid_files = []
            for i, file in enumerate(list_of_files):
                file_date = list_of_dates[i]
                if start_time - dt.timedelta(hours=file_time_threshold) <= file_date <= end_time + dt.timedelta(hours=file_time_threshold):
                    valid_files.append(file)
            list_of_files = valid_files
            if not list_of_files:
                raise MissingDataError('No MWR data found for {} {} between {} and {} (with threshold for file timestamps of {} hours)'.format(
                    self.wigos, self.inst_id, start_time, end_time, file_time_threshold))

        self.mwr_files = list_of_files
        self.alc_files = glob.glob(os.path.join(self.conf['data']['alc_dir'],
                                                '{}*{}*.nc'.format(self.conf['data']['alc_file_prefix'], self.wigos)))
        # if not self.mwr_files:
        #     err_msg = ('No MWR data for {} {} found in {}. These files must have been removed between station selection'
        #                ' and file listing. This should not happen!'.format(self.wigos, self.inst_id,
        #                                                                    self.conf['data']['mwr_dir']))
        #     # TODO: also add a CRITICAL entry with err_msg to logger before raising the exception
        #     logger.error(err_msg)
        #     raise MissingDataError(err_msg)

    # ============================================================================
    # Observations preparation methods
    # ============================================================================

    def prepare_obs(self, start_time=None, end_time=None, delete_mwr_in=False):
        """
        Prepare E-PROFILE MWR and ALC inputs.
        
        Args:
            start_time (datetime64): The start time for selecting the data.
            end_time (datetime64): The end time for selecting the data.
            delete_mwr_in (bool): Flag indicating whether to delete the MWR files after processing.
            
        Raises:
            MissingDataError: If none of the MWR files contain data between the required time limits.
            MissingDataError: If there is not enough data to run the retrieval.
        """
        start_time = np.datetime64(start_time)
        end_time = np.datetime64(end_time)

        # Load and process MWR data
        mwr = self._load_and_filter_mwr(start_time, end_time, delete_mwr_in)
        
        # Quality check of MWR data
        if self.conf['data']['check_mwr_quality']:
            self._check_mwr_data(mwr)
            
        # Calculate noise level from MWR data
        self._calculate_noise_level(mwr)
        
        # Check which scan angles are present in the mwr dataset and compare with config
        self.scan_angle_info = self._check_scan_angles(mwr)        
        
        # Extract station coordinates and validate
        self._extract_and_validate_coordinates(mwr)
        
        # Save MWR data and check surface measurements
        self._save_mwr_and_check_surface_data(mwr)
        
        # Process ALC data if available
        self._process_alc_data(start_time, end_time)

    def _load_and_filter_mwr(self, start_time, end_time, delete_mwr_in):
        """Load MWR data from files and filter by time range.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            delete_mwr_in: Whether to delete input files after processing
            
        Returns:
            xr.Dataset: Filtered MWR data
            
        Raises:
            MissingDataError: If no valid data exists in time range
        """
        mwr = get_from_nc_files(self.mwr_files)

        # Calculate time boundaries
        self.time_min = max(mwr.time.min().values, start_time)
        self.time_max = min(mwr.time.max().values, end_time)
        
        if self.time_min > self.time_max:
            logger.error('The min time exceeds the max time!')
            raise MissingDataError(f'Time range error: min_time ({self.time_min}) > max_time ({self.time_max})')
        
        self.time_mean = self.time_min + (self.time_max - self.time_min) / 2
        
        # Check if we should preserve files for future processing
        if self.time_max < mwr.time.max().values:
            delete_mwr_in = False
            logger.warning('End time is before latest data in files. Preserving files for future processing.')

        # Filter data by time range
        mwr = mwr.where((mwr.time >= self.time_min) & (mwr.time <= self.time_max), drop=True)
        mwr.time_bnds.encoding = mwr.time.encoding  # Restore encoding after filtering

        mwr.time_bnds.encoding = mwr.time.encoding
        # Add here a check on the time_min and time_max to make sure that we have at least 10 minutes of data
        # Before file deletion so that the files are kept for the next retrievals
        #TODO: Different bugs can still happen with this way of doing:
        # 1. Problem when multiple days ?
        # 2. Problem if end_time is before the mwr.time -> files from future retrievals will be deleted
        # 3. Timing problem can occur when reading delayed data (esp. when cron starts just before data arrival) 
        # --> the time min can then exceed the last time present in the mwr files...
        
        if mwr.time.size == 0:
            if delete_mwr_in:
                self._delete_files(self.mwr_files)
            logger.critical(f'None of the MWR files for {self.wigos} {self.inst_id} contains data '
                          f'between {start_time} and {end_time}')
            raise MissingDataError(f'No MWR data for {self.wigos} {self.inst_id} in time range '
                                 f'{self.time_min} to {self.time_max}')
        
        min_duration = np.timedelta64(self.conf['general']['retrieval_time'], 'm')
        data_duration = mwr.time.max().values - mwr.time.min().values

        if data_duration < self.conf['data']['mwr_obs_duration_threshold'] * min_duration:
            logger.critical('Not enough data to run the retrieval. Skipping this instrument.')
            raise MissingDataError(f'Insufficient data duration: {data_duration} < {min_duration}')
        
        # Log successful data loading
        logger.info('=' * 90)
        logger.info(f'Data retrieval from {mwr.title} between '
                   f'{datetime64_to_str(self.time_min, "%Y-%m-%d %H:%M:%S")} and '
                   f'{datetime64_to_str(self.time_max, "%Y-%m-%d %H:%M:%S")}')
        
        if delete_mwr_in:
            self._delete_files(self.mwr_files)
        
        return mwr

    def _check_mwr_data(self, mwr):
        """Validate MWR data quality and metadata.
        
        Args:
            mwr: MWR dataset to validate
            
        Raises:
            MissingDataError: If validation fails
        """
        # TODO: uncomment the following block once getting good test files with ok quality flags
        mwr['tb'] = mwr.tb.where(mwr.quality_flag == 0)
        if mwr.tb.isnull().all():
            raise MissingDataError(f'All MWR brightness temperature observations between '
                                   f'{self.time_min} and {self.time_max} are flagged.')

    def _calculate_noise_level(self, mwr):
        """Calculate noise level from MWR data and add to dataset.
        
        Args:
            mwr: MWR dataset to process
        """
        # Calculate noise level as standard deviation of brightness temperature for each channel at zenith (or near-zenith) angles, ignoring NaNs
        noise_level = mwr.tb.where(np.abs(mwr.ele - 90) < 1).std(dim='time', skipna=True)
        mwr['noise_level'] = noise_level
        mwr.noise_level.attrs['units'] = 'K'
        mwr.noise_level.attrs['long_name'] = 'Estimated noise level of tb observations'

    def _check_scan_angles(self, mwr):
        """Check which scan angles are present in MWR data and compare with instrument config.
        
        This method identifies the unique elevation angles present in scanning observations
        and compares them with the scan_channels specified in the instrument configuration.
        It logs warnings if there are mismatches and updates flags accordingly.
        
        Args:
            mwr: MWR dataset to analyze
            
        Returns:
            dict: Dictionary with keys 'available_angles', 'expected_angles', 'missing_angles', 'extra_angles'
        """
        # Get scan angles from MWR data (only scanning observations, not zenith)
        
        scan_freq_sel = self.inst_conf['retrieval'].get('scan_channels', [])
        scan_data = mwr.where(mwr.pointing_flag == 1, drop=True).sel(frequency=scan_freq_sel)
        
        if not has_data(scan_data, 'tb'):
            logger.warning('No scanning observations found in MWR data')
            return {
                'available_angles': [],
                'expected_angles': self.inst_conf['retrieval'].get('scan_ele', []),
                'missing_angles': self.inst_conf['retrieval'].get('scan_ele', []),
                'extra_angles': []
            }
            
        # Check that the scan data brightness temperature in "scan channels" are not empty
        
        
        # Get unique elevation angles from the data (rounded to 1 decimal to handle small variations)
        available_angles = np.unique(np.round(scan_data.ele.values, 1))
        available_angles = available_angles[~np.isnan(available_angles)]  # Remove NaN values
        available_angles = available_angles[np.abs(90 - available_angles) > 1] 
        available_angles = sorted(available_angles.tolist())
        
        # Get expected scan angles from instrument config
        expected_angles = self.inst_conf['retrieval'].get('scan_ele')
        
        # If scan_channels is not defined in config, log warning and return
        if len(expected_angles)==0:
            logger.warning('No scan_channels defined in instrument configuration. '
                         f'Found the following elevation angles in data: {available_angles}')
            return {
                'available_angles': available_angles,
                'expected_angles': [],
                'missing_angles': [],
                'extra_angles': available_angles
            }
        
        # Convert expected angles to set for comparison (rounded to match data processing)
        expected_angles_set = set(np.round(expected_angles, 0))
        available_angles_set = set(np.round(available_angles, 0))  
        
        # Find missing and extra angles
        missing_angles = sorted(list(expected_angles_set - available_angles_set))
        extra_angles = sorted(list(available_angles_set - expected_angles_set))
        
        # Log results
        logger.info(f'Scan angle check:')
        logger.info(f'Expected angles from config: {sorted(list(expected_angles_set))}')
        logger.info(f'Available angles in data: {available_angles_set}')
        
        if missing_angles:
            logger.warning(f'  Missing scan angles (in config but not in data): {missing_angles}')
        
        if extra_angles:
            logger.warning(f'  Extra scan angles (in data but not in config): {extra_angles}')
        
        if not missing_angles and not extra_angles:
            logger.info('   All expected scan angles are present in the data')
        
        # Count observations per angle for diagnostic purposes
        logger.debug('Observations per elevation angle:')
        for angle in available_angles:
            count = np.sum(np.abs(scan_data.ele.values - angle) < 1)
            logger.debug(f'  {angle:5.1f}°: {count} observations')
        
        return {
            'available_angles': available_angles,
            'expected_angles': sorted(list(expected_angles_set)),
            'missing_angles': missing_angles,
            'extra_angles': extra_angles
        }

    def _extract_and_validate_coordinates(self, mwr):
        """Extract station coordinates from MWR data and validate against config.
        
        Args:
            mwr: MWR dataset
            
        Raises:
            MissingDataError: If coordinates don't match config within tolerance
        """
        # Validate WIGOS ID
        if mwr.wigos_station_id != self.wigos:
            logger.error(f'WIGOS ID mismatch: file has {mwr.wigos_station_id}, '
                        f'expected {self.wigos}')
            raise MissingDataError(f'WIGOS ID mismatch: {mwr.wigos_station_id} != {self.wigos}')
        
        # Get tolerances from config (already defined in data section)
        tolerance_lat_lon = self.conf['data']['tolerance_lat_lon']
        tolerance_alt = self.conf['data']['tolerance_alt']
        
        # Extract coordinates (using median to be robust against outliers)
        self.station_latitude = np.nanmedian(mwr.station_latitude.values)
        self.station_longitude = np.nanmedian(mwr.station_longitude.values)
        self.station_altitude = np.nanmedian(mwr.station_altitude.values)

        # Validate coordinates
        lat_diff = abs(self.station_latitude - self.inst_conf['station_latitude'])
        lon_diff = abs(self.station_longitude - self.inst_conf['station_longitude'])
        alt_diff = abs(self.station_altitude - self.inst_conf['station_altitude'])
        
        if lat_diff > tolerance_lat_lon or lon_diff > tolerance_lat_lon or alt_diff > tolerance_alt:
            logger.error(f'Station coordinate mismatch: '
                        f'lat_diff={lat_diff:.3f}, lon_diff={lon_diff:.3f}, alt_diff={alt_diff:.1f}m')
            raise MissingDataError('Station coordinates in MWR file do not match config file '
                                 f'(tolerances: {tolerance_lat_lon}°, {tolerance_alt}m)')

    def _save_mwr_and_check_surface_data(self, mwr):
        """Save MWR data to file and check availability of surface measurements.
        
        Args:
            mwr: MWR dataset to save
        """
        mwr.time_bnds.encoding = mwr.time.encoding
        mwr.to_netcdf(self.mwr_file_tropoe)

        # Check which surface measurements are available
        self.sfc_temp_obs_exists = has_data(mwr, 'air_temperature')
        self.sfc_rh_obs_exists = has_data(mwr, 'relative_humidity')
        self.sfc_p_obs_exists = has_data(mwr, 'air_pressure')
        
        # station_pressure is required by TROPoe, therefore we will calculate a default one based on the station altitude and a standard atmosphere if no pressure observations are available
        station_pressure_std_atm, self.station_psfc_min, self.station_psfc_max = calculate_pressure_from_std_atmosphere(self.station_altitude)  
  
        if self.sfc_p_obs_exists:
            self.station_pressure = np.nanmedian(mwr.air_pressure.values)
        else:
            self.station_pressure = station_pressure_std_atm
            logger.warning(f'No pressure observations available. Calculated station pressure from altitude: {self.station_pressure:.1f} hPa')

        self.mwr = mwr

    def _process_alc_data(self, start_time, end_time):
        """Process ceilometer (ALC) data if available.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
        """
        tolerance_alc_time = np.timedelta64(self.conf['data']['alc_time_tolerance_minutes'], 'm')
        
        self.alc_exists = False
        
        if not self.alc_files:
            logger.debug('No ALC files available')
            return
        
        try:
            # MeteoSwiss daily concat files have calendar issues. Use instant files or concat at CEDA
            alc = get_from_nc_files(self.alc_files)
            alc = alc.where((alc.time >= self.time_min - tolerance_alc_time) &
                           (alc.time <= self.time_max + tolerance_alc_time), drop=True)
            
            if alc.time.size > 0:
                alc.to_netcdf(self.alc_file_tropoe)
                self.alc_exists = True
                logger.info(f'ALC data available: {alc.time.size} timesteps')
            else:
                logger.info('ALC files found but no data in time range')
        except Exception as e:
            logger.warning(f'Failed to process ALC data: {e}')
            self.alc_exists = False

    def _delete_files(self, file_list):
        """Safely delete a list of files with logging.
        
        Args:
            file_list: List of file paths to delete
        """
        for filepath in file_list:
            try:
                os.remove(filepath)
                logger.debug(f'Deleted file: {filepath}')
            except OSError as e:
                logger.warning(f'Failed to delete {filepath}: {e}')

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

    def prepare_model(self, OmB=False):
        """extract reference profile and uncertainties as well as surface data from ECMWF to files readable by TROPoe"""
        model = ModelInterpreter(self.model_fc_file, self.model_zg_file)
        model.run(self.time_min, self.time_max)
        prof_data, sfc_data = model_to_tropoe(model, station_altitude=self.inst_conf['station_altitude'], OmB=OmB)
        prof_data.to_netcdf(self.model_prof_file_tropoe)
        self.met_sfc_offset = int(1e3*sfc_data.height.mean(dim='time').data)
        if not self.has_complete_surface_data:
            sfc_data.to_netcdf(self.model_sfc_file_tropoe)
        
    def prepare_vip(self):
        """Prepare the VIP configuration file for running the TROPoe container.
        
        This method has been refactored to use helper functions from tropoe_helpers.py
        for better modularity and testability.
        """
        # Prepare parameters for helper function
        station_coords = {
            'latitude': self.station_latitude,
            'longitude': self.station_longitude,
            'altitude': self.station_altitude,
            'pressure': self.station_pressure,
            'station_psfc_min': self.station_psfc_min,
            'station_psfc_max': self.station_psfc_max
        }
        
        tropoe_paths = {
            'mountpoint': self.tropoe_dir_mountpoint,
            'mwr_basename': self.conf['data']['mwr_basefilename_tropoe']
        }
        
        # Update the scan related parameters in self.inst_conf based on actual scan data in mwr:
        self.inst_conf['retrieval']['scan_ele'] = self.scan_angle_info['available_angles']
        
        # Build VIP configuration using helper function from tropoe_helpers
        vip_full, sfc_data_type = build_vip_config(
            mwr_data=self.mwr,
            inst_conf=self.inst_conf,
            station_coords=station_coords,
            has_surface_data=self.has_complete_surface_data,
            met_sfc_offset=self.met_sfc_offset,
            tropoe_paths=tropoe_paths,
            output_basename=self.tropoe_output_basename,
            retrieval_conf=self.conf
        )
        
        # Store surface data type for later use
        self.ext_sfc_data_type = sfc_data_type
        
        # Write VIP file using helper function from tropoe_helpers
        write_vip_file(vip_full, self.vip_file_tropoe)

    def do_retrieval(self):
        """run the retrieval using the TROPoe container"""
        # TODO: decide which a-priori file to use. associate with inst or general? where to store this config:
        #  inst config file, some DB or a apriori config file with info for all instruments
        apriori_file = self.conf['data']['default_apriori_file']  # located outside TROPoe container unless starting with prior.*
        date = datetime64_to_str(self.time_mean, '%Y%m%d')
        run_tropoe(self.tropoe_dir, date, datetime64_to_hour(self.time_min), datetime64_to_hour(self.time_max),
                   self.vip_file_tropoe, apriori_file, tropoe_img=self.conf['data']['tropoe_img'], 
                   verbosity=self.conf['data']['tropoe_verbosity'])
        
    def postprocess_tropoe(self):
        """Post-process TROPoe outputs and write to NetCDF file matching the E-PROFILE format."""
        logger.info('Post-processing TROPoe output')
        
        # Find and load TROPoe output file
        tropoe_output_file = self._find_tropoe_output_file()
        tropoe_data = xr.open_dataset(tropoe_output_file)
        
        # Load configuration files for transformation and output
        tropoe_out_config = get_conf(abs_file_path(f'mwr_l12l2/config/{self.conf["general"]["TROPoe_output_config_file"]}'))
        eprofile_l2_config = get_nc_format_config(abs_file_path(f"mwr_l12l2/config/{self.conf['general']['L2_format_config_file']}"))
        
        # Transform data using helper
        data = convert_tropoe_output(
            retrieval_conf=self.conf,
            tropoe_data=tropoe_data,
            mwr_l1_data=self.mwr,
            tropoe_out_config=tropoe_out_config,
            use_model_data=self.use_model_data,
            ext_sfc_data_type=self.ext_sfc_data_type
        )
        
        # Add the time_bnds variable based on the data time dimension and the tresolution defined in the config file:
        time_bnds = self.calculate_time_bnds(data.time, self.conf['general']['retrieval_time'])
        data = data.assign(time_bnds=time_bnds)
        
        # Complete the derived_variables and add the retrieval_type attribute to them
        derived_product_list = self.conf['data']['derived_product_list']
        data = self.derived_variables(data, derived_product_list)
        
        # If provided, crop to max altitude defined in config file
        max_altitude_magl = self.conf['data']['max_altitude_magl']
        if max_altitude_magl is not None:
            logger.info(f'Cropping data to max altitude: {max_altitude_magl} m')
            # find the indices where altitude is above max_altitude_magl + station_altitude and drop them
            # we need to do this because we have both altitude and avk_altitude dimensions
            ind_alt_max = np.argwhere(data.altitude.data > (max_altitude_magl + self.station_altitude))

            data = data.isel(altitude=slice(0, ind_alt_max[0][0])).isel(avk_altitude=slice(0, ind_alt_max[0][0]))  # keep all indices below the first index where altitude exceeds max_altitude_magl + station_altitude

        # Write output file
        output_filename = self._write_eprofile_l2(data, conf_nc=eprofile_l2_config)
        
        # Upload to S3 if configured
        if self._should_upload_to_s3():
            self._upload_to_s3(output_filename, tropoe_output_file)
    
    def derived_variables(self, data, derived_product_list):
        
        logger.info(f'Calculating or completing derived products: {derived_product_list}')
        
        for var in derived_product_list:
            if var not in data.variables:
                try:
                    data = calculate_derived_product(data, var)
                except Exception as e:
                    logger.error(f'Error calculating derived variable {var}: {e}')
            
            # Also, all derived producs must have an associated "sigma_{var}" and "systematic_{var}" variable for the uncertainty. We will check if these variables exist and if not create them with NaN values and the right dimensions and attributes:
            sigma_var = 'sigma_' + var
            if sigma_var not in data.variables:
                data = data.assign({sigma_var: (data[var].dims, np.full(data[var].shape, np.nan))})
                data[sigma_var].attrs['units'] = data[var].attrs.get('units', '')  # use same units as the variable if defined
            
            data[var].attrs['retrieval_type'] = 'derived product'
            data[sigma_var].attrs['retrieval_type'] = 'derived product'
        return data
    
    def calculate_time_bnds(self, time, tresolution_minutes):
        """Calculate time bounds for each time step based on the specified time resolution.
        
        Args:
            time: xarray DataArray of time steps
            tresolution_minutes: Time resolution in minutes
            
        Returns:
            xarray DataArray of time bounds with dimensions (time, 2)
        """

        avg_time = np.timedelta64(int(tresolution_minutes * 60), 's')
        time_bnds = xr.DataArray(
            data=np.array([time, time + avg_time]).transpose(),
            coords={'time': time},
            dims=['time', 'bnds'],
        )
        return time_bnds
        
    def _find_tropoe_output_file(self):
        """Find the TROPoe output file.
        
        Returns:
            str: Path to TROPoe output file
            
        Raises:
            MWRRetrievalError: If no output file or multiple output files are found
        """
        outfiles_pattern = os.path.join(self.tropoe_dir, self.tropoe_output_basename + '*.nc')
        outfiles = glob.glob(outfiles_pattern)
        
        if len(outfiles) == 0:
            raise MWRRetrievalError(
                f'Found no file matching {outfiles_pattern}. '
                'Possibly TROPoe did not run through.')
        elif len(outfiles) > 1:
            raise MWRRetrievalError(
                f"Found several files matching {outfiles_pattern}. "
                "Don't know which TROPoe output to use.")
        
        return outfiles[0]
    
    def _write_eprofile_l2(self, data, conf_nc):
        """Write processed data to E-Profile L2 format NetCDF file.
        
        Args:
            data: xarray Dataset to write
            conf_nc: NetCDF format configuration
        Returns:
            str: Path to output file
        """        
        basename = os.path.join(
            self.conf['data']['output_dir'], 
            self.conf['data']['output_file_prefix'] + self.wigos + '_' + self.inst_id
        )
        
        # TODO: use actual retrieved period instead of mwr_files for filename
        filename = generate_output_filename(
            basename, 
            'time_min', 
            time=data.time
        )
        
        nc_writer = Writer(data, filename, conf_nc)
        nc_writer.run()
        
        logger.info(f'E-PROFILE output written to {filename}')
        return filename
    
    def _should_upload_to_s3(self):
        """Check if S3 upload is configured.
        
        Returns:
            bool: True if S3 upload should be performed
        """
        return ('output_bucket_copy' in self.conf['data'] and 
                'bucket_credentials' in self.conf['data'])
    
    def _upload_to_s3(self, eprofile_file, tropoe_file):
        """Upload output files to S3 bucket.
        
        Args:
            eprofile_file: Path to E-PROFILE output file
            tropoe_file: Path to raw TROPoe output file
        """
        if not os.path.isfile(eprofile_file):
            logger.warning(f'E-PROFILE output file {eprofile_file} not found. Skipping S3 upload.')
            return
        
        try:
            # Load S3 credentials
            config_credentials_file = self.conf['data']['bucket_credentials']
            s3_config = self._load_s3_credentials(config_credentials_file)
            
            # Create S3 client
            s3 = boto3.client(
                's3',
                endpoint_url=s3_config['endpoint'],
                aws_access_key_id=s3_config['access_key_id'],
                aws_secret_access_key=s3_config['secret_access_key']
            )
            
            bucket_name = self.conf['data']['output_bucket_copy']
            
            # Upload E-PROFILE output
            s3_key = 'rs-comp/'+os.path.basename(eprofile_file)
            s3.upload_file(eprofile_file, bucket_name, s3_key)
            logger.info(f'Uploaded E-PROFILE output to S3: {bucket_name}/{s3_key}')
            
            # Upload TROPoe output
            s3_key_tropoe = 'rs-comp/'+os.path.basename(tropoe_file)
            s3.upload_file(tropoe_file, bucket_name, s3_key_tropoe)
            logger.info(f'Uploaded TROPoe output to S3: {bucket_name}/{s3_key_tropoe}')
            
        except Exception as e:
            logger.error(f'Failed to upload files to S3 bucket: {e}')
    
    def _load_s3_credentials(self, credentials_file):
        """Load S3 credentials from configuration file.
        
        Args:
            credentials_file: Path to credentials file
            
        Returns:
            dict: Credentials dictionary with keys 'access_key_id', 'secret_access_key', 'endpoint'
        """
        config = {}
        with open(credentials_file, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    config[key.strip()] = value.strip()
        
        return {
            'access_key_id': config['access_key'],
            'secret_access_key': config['secret_key'],
            'endpoint': config['host_base']
        }
