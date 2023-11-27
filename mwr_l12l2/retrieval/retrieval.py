import glob
import os
import shutil

import datetime as dt
import numpy as np
import xarray as xr

from mwr_l12l2.errors import MissingDataError, MWRConfigError, MWRInputError, MWRRetrievalError
from mwr_l12l2.log import logger
from mwr_l12l2.model.ecmwf.interpret_ecmwf import ModelInterpreter
from mwr_l12l2.retrieval.tropoe_helpers import model_to_tropoe, run_tropoe, transform_units, height_to_altitude, extract_prior, extract_attrs
from mwr_l12l2.utils.config_utils import get_retrieval_config, get_inst_config, get_nc_format_config, get_conf
from mwr_l12l2.utils.data_utils import datetime64_to_str, get_from_nc_files, has_data, datetime64_to_hour, \
    scalars_to_time, vectors_to_time
from mwr_l12l2.utils.file_utils import abs_file_path, concat_filename, datetime64_from_filename, dict_to_file, \
    generate_output_filename
from mwr_l12l2.write_netcdf import Writer


class Retrieval(object):
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
        self.sfc_temp_obs_exists = None  # is temperature measured by met station of MWR instrument?
        self.sfc_rh_obs_exists = None  # is rel humidity measured by met station of MWR instrument?
        self.sfc_p_obs_exists = None  # is pressure measured by met station of MWR instrument?
        self.alc_exists = None  # is cloud base measured by co-located ceilometer?

        # set by choose_mode_files():
        self.model_fc_file = None
        self.model_zg_file = None

    def run(self, start_time=None, end_time=None):
        """run the entire retrieval chain

        Args:
            start_time (optional): earliest time from which to consider data. If not specified, all data younger than
                'max_age' specified in retrieval config will be used or, if 'max_age' is None, age of data is unlimited.
            end_time (optional): latest time from which to consider data. If not specified, all data received by now is
                processed.
        """
        if start_time is not None and not isinstance(start_time, dt.datetime):
            raise MWRInputError("input argument 'start_time' is expected to be of type datetime.datetime or None")
        if start_time is None and self.conf['data']['max_age'] is not None:
            logger.info('No start time provided. Using data from the last {} minutes.'.format(self.conf['data']['max_age']))
            start_time = dt.datetime.utcnow() - dt.timedelta(minutes=self.conf['data']['max_age'])
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
        
        # New flag for the use of the model data as pseudo observation
        if self.conf['vip']['mod_temp_prof_type'] != 0 or self.conf['vip']['mod_wv_prof_type'] != 0:
            self.use_model_data = True
        else:
            self.use_model_data = False

        # We also read the model if there are no mwr met station 
        if  self.use_model_data or \
                not (self.sfc_temp_obs_exists & self.sfc_rh_obs_exists & self.sfc_p_obs_exists):
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

    def prepare_paths(self, datestamp='', netcdf_ext='.nc'):
        """prepare input and output paths and filenames from config"""
        self.tropoe_dir = os.path.join(self.conf['data']['tropoe_basedir'],
                                       '{}{}/'.format(self.conf['data']['tropoe_subfolder_basename'], self.node))
        self.vip_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['vip_filename_tropoe'])
        self.mwr_file_tropoe = os.path.join(self.tropoe_dir,
                                            self.conf['data']['mwr_basefilename_tropoe'] + datestamp + netcdf_ext)
        self.alc_file_tropoe = os.path.join(self.tropoe_dir,
                                            self.conf['data']['alc_basefilename_tropoe'] + datestamp + netcdf_ext)
        self.model_prof_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['model_prof_basefilename_tropoe']
                                                   + datestamp + netcdf_ext)
        self.model_sfc_file_tropoe = os.path.join(self.tropoe_dir, self.conf['data']['model_sfc_basefilename_tropoe']
                                                  + datestamp + netcdf_ext)
        self.tropoe_dir_mountpoint = self.conf['data']['tropoe_dir_mountpoint']

    def prepare_tropoe_dir(self):
        """set up an empty tropoe tmp file directory for the current node (remove old one if existing)"""
        if os.path.exists(self.tropoe_dir):
            shutil.rmtree(self.tropoe_dir)
        os.mkdir(self.tropoe_dir)

    def select_instrument(self):
        """select instrument which has oldest (processable) mwr file in input dir"""
        # TODO: implement this
        # TODO: Need to lock lookup for station selection for other nodes until prepare_eprofile_main with delete_mwr_in
        #       is done. Something like https://stackoverflow.com/questions/52815858/python-lock-directory might work.
        #       but better use ecflow to not data listing for other nodes until end of prepare_eprofile_main
        # find oldest file in the folder and get station id from filename (or from file content)
        # list files in input dir
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                               '{}*.nc'.format(self.conf['data']['mwr_file_prefix'])))
        
        if not list_of_files:
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

    def list_obs_files(self):
        """get file lists for the selected station

        Note:
             this method shall list all (MWR) files not just the ones matching time settings. Like that old (obsolete)
             files are removed when :meth:`prepare_obs` is run with delete_mwr_in=True
        """
        self.mwr_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                                '{}*{}_{}*.nc'.format(self.conf['data']['mwr_file_prefix'],
                                                                      self.wigos, self.inst_id)))
        self.alc_files = glob.glob(os.path.join(self.conf['data']['alc_dir'],
                                                '{}*{}*.nc'.format(self.conf['data']['alc_file_prefix'], self.wigos)))
        if not self.mwr_files:
            err_msg = ('No MWR data for {} {} found in {}. These files must have been removed between station selection'
                       ' and file listing. This should not happen!'.format(self.wigos, self.inst_id,
                                                                           self.conf['data']['mwr_dir']))
            # TODO: also add a CRITICAL entry with err_msg to logger before raising the exception
            raise MissingDataError(err_msg)

    def prepare_obs(self, start_time=None, end_time=None, delete_mwr_in=False):
        """function preparing E-PROFILE MWR and ALC inputs (concatenate to one file, select time, saving)"""

        tolerance_alc_time = np.timedelta64(5, 'm')  # get ALC up to 5 minutes before/after start/end of MWR interval

        start_time = np.datetime64(start_time)
        end_time = np.datetime64(end_time)

        # MWR treatment
        mwr = get_from_nc_files(self.mwr_files)

        self.time_min = max(mwr.time.min().values, start_time) 
        self.time_max = min(mwr.time.max().values, end_time)
        self.time_mean = self.time_min + (self.time_max - self.time_min) / 2  # need to work with diff to get timedelta 
        
        # If the provided end_time is smaller than the time present in the mwr files, we should not delete the files
        if end_time < mwr.time.max().values:
            Warning('The provided end_time is smaller than the time present in the mwr files. ')

        mwr = mwr.where((mwr.time >= self.time_min) & (mwr.time <= self.time_max),
                        drop=True)  # brackets because of precedence of & over > and <
        
        # Add here a check on the time_min and time_max to make sure that we have at least 10 minutes of data
        # Before file deletion so that the files are kept for the next retrievals
        #TODO: Different bugs can still happen with this way of doing:
        # 1. Problem when multiple days ?
        # 2. Problem if end_time is before the mwr.time -> files from future retrievals will be deleted
        if mwr.time.size == 0:  # this must happen after file deletion to avoid useless files persist in input dir
            if delete_mwr_in:
                for file in self.mwr_files:
                    os.remove(file)
            raise MissingDataError('None of the MWR files found for {} {} contains data between the required time '
                                   'limits (min={}; max={})'.format(self.wigos, self.inst_id, start_time, end_time))
        elif (mwr.time.max().values - mwr.time.min().values) < np.timedelta64(self.conf['vip']['tres'], 'm'):
            raise MissingDataError('Not enough data to run the retrieval. Skipping this instrument.')
        else:
            logger.info('#############################################################################################')
            logger.info('Data retrieval from '+mwr.title+' between '+datetime64_to_str(mwr.time.min().values, '%Y-%m-%d %H:%M:%S')+' and '+datetime64_to_str(mwr.time.max().values, '%Y-%m-%d %H:%M:%S'))
            if delete_mwr_in:
                for file in self.mwr_files:
                    os.remove(file)

        # if mwr.time.size == 0:  # this must happen after file deletion to avoid useless files persist in input dir
        #     raise MissingDataError('None of the MWR files found for {} {} contains data between the required time '
        #                            'limits (min={}; max={})'.format(self.wigos, self.inst_id, start_time, end_time))

        # TODO: uncomment the following block once getting good test files with ok quality flags
        # mwr['tb'] = mwr.tb.where(mwr.quality_flag == 0)
        # if mwr.tb.isnull().all():
        #     raise MissingDataError('All MWR brightness temperature observations between {} and {} are flagged. '
        #                            'Nothing to retrieve!'.format(start_time, end_time))

        # Check if the wigos id is the correct one:
        if mwr.wigos_station_id != self.wigos:
            raise MissingDataError('The wigos id in the MWR file ({}) does not match the one in the config file ({})'
                                   .format(mwr.wigos_station_id, self.wigos))

        # Check if the latitute, longitude and altitude of the station correspond to the ones in the config file:
        # with tolerance of 0.5 degree for lat and lon and 50 m for alt:
        tolerance_lat_lon = self.conf['data']['tolerance_lat_lon'] 
        tolerance_alt = self.conf['data']['tolerance_alt'] 

        if (abs(np.nanmedian(mwr.station_latitude.values) - self.inst_conf['station_latitude']) > tolerance_lat_lon) | \
                (abs(np.nanmedian(mwr.station_longitude.values) - self.inst_conf['station_longitude']) > tolerance_lat_lon) | \
                (abs(np.nanmedian(mwr.station_altitude.values) - self.inst_conf['station_altitude']) > tolerance_alt):
            raise MissingDataError('The station coordinates in the MWR file do not match the ones in the config file')
        
        mwr.to_netcdf(self.mwr_file_tropoe)

        self.sfc_temp_obs_exists = has_data(mwr, 'air_temperature')
        self.sfc_rh_obs_exists = has_data(mwr, 'relative_humidity')
        self.sfc_p_obs_exists = has_data(mwr, 'air_pressure')

        self.mwr = mwr

        # ALC treatment
        self.alc_exists = True  # start assuming ALC obs exist, set to False if not.
        if self.alc_files:  # not empty list, not None
            # careful: MeteoSwiss daily concat files have problem with calendar. Use instant files or concat at CEDA
            alc = get_from_nc_files(self.alc_files)
            alc = alc.where((alc.time >= self.time_min - tolerance_alc_time)
                            & (alc.time <= self.time_max + tolerance_alc_time), drop=True)
            if alc.time.size == 0:
                self.alc_exists = False
            else:
                alc.to_netcdf(self.alc_file_tropoe)
        else:
            self.alc_exists = False

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

    def prepare_model(self):
        """extract reference profile and uncertainties as well as surface data from ECMWF to files readable by TROPoe"""
        model = ModelInterpreter(self.model_fc_file, self.model_zg_file)
        model.run(self.time_min, self.time_max)
        prof_data, sfc_data = model_to_tropoe(model, station_altitude=self.inst_conf['station_altitude'])
        prof_data.to_netcdf(self.model_prof_file_tropoe)
        self.met_sfc_offset = int(sfc_data.height.mean(dim='time').data)
        if not (self.sfc_temp_obs_exists & self.sfc_rh_obs_exists & self.sfc_p_obs_exists):
            sfc_data.to_netcdf(self.model_sfc_file_tropoe)
        
    def prepare_vip(self):
        """prepare the vip configuration file for running the TROPoe container"""
        # TODO: would be more readable to transform this to a helper function in tropoe_helpers. does not set anything
        #  to self, just uses it. very simple task

        header = '# This file is automatically generated. Do not edit. To change settings modify retrieval config file.'
        ch_zenith = self.inst_conf['retrieval']['zenith_channels']
        ch_scan = self.inst_conf['retrieval']['scan_channels']

        # final check of inst config file
        if not (len(ch_zenith) == len(ch_scan) == len(self.mwr.frequency)):
            err_msg_1 = ('Length of zenith_channels ({}) and scan_channels ({}) in instrument config must match length '
                         'of frequency dimension in level 1 data file ({}).'.format(len(ch_zenith), len(ch_scan),
                                                                                    len(self.mwr.frequency)))
            err_msg_2 = 'This is not the case for {}_{}'.format(self.wigos, self.inst_id)
            raise MWRConfigError(' '.join([err_msg_1, err_msg_2]))

        # Check for met data in the mwr level 1, if exist setup VIP file accordingly to read mwr level 1 file for 
        # surface data and if not taking lowest model level as surface data (with altitude offset)
        if self.sfc_temp_obs_exists & self.sfc_rh_obs_exists & self.sfc_p_obs_exists:
            logger.info('Surface data measured by the MWR')
            self.ext_sfc_data_type = 4
            sfc_data_offset = 0
            sfc_rootname = "mwr"
        else: 
            logger.info('No surface data measured by the MWR, using the forecast data instead')
            self.ext_sfc_data_type = 1
            sfc_data_offset = self.met_sfc_offset
            sfc_rootname = "met"  # this should be the default value but better specify

        # update and complete vip entries with info from conf and data availability
        vip_edits = dict(mwr_n_tb_fields=len(self.mwr.frequency[ch_zenith]),
                         mwr_tb_freqs=self.mwr.frequency[ch_zenith].values,
                         mwr_tb_noise=self.inst_conf['retrieval']['tb_noise'][ch_zenith],
                         mwr_tb_bias=self.inst_conf['retrieval']['tb_bias'][ch_zenith],
                         station_psfc_max=1030.,  # TODO: calc from station altitude
                         station_psfc_min=800.,
                         ext_sfc_wv_type=self.ext_sfc_data_type,  # 4 for mwr file, 1 for model file
                         ext_sfc_temp_type=self.ext_sfc_data_type,  # 4 for mwr file, 1 for model file
                         ext_sfc_relative_height=sfc_data_offset,
                         ext_sfc_rootname=sfc_rootname,
                         # TODO check what happens with surface pressure
                         mwr_path=self.tropoe_dir_mountpoint,
                         mwr_rootname=self.conf['data']['mwr_basefilename_tropoe'],
                         mwrscan_path=self.tropoe_dir_mountpoint,
                         mwrscan_rootname=self.conf['data']['mwr_basefilename_tropoe'],
                         mod_temp_prof_path=self.tropoe_dir_mountpoint,
                         mod_wv_prof_path=self.tropoe_dir_mountpoint,
                         cbh_path=self.tropoe_dir_mountpoint,  # if no ALC is available, TROPoe uses default cbh of 2 km
                         ext_sfc_path=self.tropoe_dir_mountpoint,
                         output_path=self.tropoe_dir_mountpoint,
                         output_rootname=self.tropoe_output_basename,
                         )
        
        # Add scan variables to the VIP file only if they exist
        if any(ch_scan):
            logger.info('Found scan data measured by the MWR')
            vip_edits['mwrscan_type']=4
            vip_edits['mwrscan_elev_field']='ele'
            vip_edits['mwrscan_freq_field']='frequency'
            vip_edits['mwrscan_tb_field_names']='tb'
            vip_edits['mwrscan_tb_field1_tbmax']=330.
            vip_edits['mwrscan_time_delta']=0.25
            vip_edits['mwrscan_elevations']=self.inst_conf['retrieval']['scan_ele']
            vip_edits['mwrscan_n_elevations']=len(self.inst_conf['retrieval']['scan_ele'])
            vip_edits['mwrscan_n_tb_fields']=len(self.mwr.frequency[ch_scan])
            vip_edits['mwrscan_tb_freqs']=self.mwr.frequency[ch_scan].values
            vip_edits['mwrscan_tb_noise']=self.inst_conf['retrieval']['tb_noise'][ch_scan]
            vip_edits['mwrscan_tb_bias']=self.inst_conf['retrieval']['tb_bias'][ch_scan]
        else: 
            logger.info('No scan available for this retrieval')
        self.conf['vip'].update(vip_edits)
        dict_to_file(self.conf['vip'], self.vip_file_tropoe, sep=' = ', header=header,
                     remove_brackets=True, remove_parentheses=True, remove_braces=True)

    def do_retrieval(self):
        """run the retrieval using the TROPoe container"""
        # TODO: decide which a-priori file to use. associate with inst or general? where to store this config:
        #  inst config file, some DB or a apriori config file with info for all instruments
        apriori_file = 'prior.MIDLAT.nc'  # located outside TROPoe container unless starting with prior.*
        date = datetime64_to_str(self.time_mean, '%Y%m%d')
        run_tropoe(self.tropoe_dir, date, datetime64_to_hour(self.time_min), datetime64_to_hour(self.time_max),
                   self.vip_file_tropoe, apriori_file, verbosity=1)

    def postprocess_tropoe(self):
        """post-process the outputs of TROPoe and write to NetCDF file matching the E-PROFILE format"""
        # TODO: set up a writer producing the E-PROFILE format. 90% of mwr_raw2l1.write_netcdf() and
        #  mwr_raw2l1.config.L2_format.yaml will be re-usable by just modifying the .yaml to match TROPoe output vars to
        #  the output format varnames and attributes
        logger.info('Post-processing TROPoe output')
        outfiles_pattern = os.path.join(self.tropoe_dir, self.tropoe_output_basename + '*.nc')
        outfiles = glob.glob(outfiles_pattern)
        if len(outfiles) == 1:
            data = xr.open_dataset(outfiles[0])
        elif len(outfiles) == 0:
            raise MWRRetrievalError('Found no file matching {}. Possibly the TROPoe did not run through.'.format(
                outfiles_pattern))
        elif len(outfiles) > 1:
            raise MWRRetrievalError("Found several files matching {}. Don't know which TROPoe output to use.".format(
                outfiles_pattern))

        tropoe_out_config = get_conf(abs_file_path('mwr_l12l2/config/tropoe_output_config.yaml'))

        # Some variables needs to be extracted from TROPoe output (e.g. prior for each quantity)
        data = extract_prior(data, tropoe_out_config) 

        # Some variables needs to be propagated from L1
        # e.g azi
        #data['azi'] = self.mwr.azi
        
        data = transform_units(data)

        data = height_to_altitude(data, self.mwr.station_altitude)
        data = scalars_to_time(data, ['lat', 'lon', 'station_altitude','lwp_prior'])  # to be executed after height_to_altitude
        data = vectors_to_time(data, ['temperature_prior', 'waterVapor_prior']) 
        # TODO: add postprocessing calculations for derived quantities, e.g. forecast indices

        # propagate some (all ?) metadata from L1 to L2
        for attr in self.mwr.attrs:
            data.attrs[attr] = self.mwr.attrs[attr]

        # Some extra attributes that are needed and which can be derived from the data (also renaming of some TROPoe attrs)
        data = extract_attrs(data)

        if self.use_model_data:
            data.attrs['retrieval_type'] = '1DVAR'
        else:
            data.attrs['retrieval_type'] = 'optimal estimation'

        if self.ext_sfc_data_type == 1:
            data.attrs['ext_sfc_temp_type'] = 'model'
            data.attrs['ext_sfc_wv_type'] = 'model'
        elif self.ext_sfc_data_type == 4:
            data.attrs['ext_sfc_temp_type'] = 'mwr'
            data.attrs['ext_sfc_wv_type'] = 'mwr'
        else:
            data.attrs['ext_sfc_temp_type'] = 'unknown'
            data.attrs['ext_sfc_wv_type'] = 'unknown'

        # Remove uncesseray attrs from data (all containinins "VIP")
        for attr in list(data.attrs):
            if 'VIP' in attr:
                del data.attrs[attr]
        
        # write output  # TODO probably better split into seperate method
        nc_format_config_file = abs_file_path('mwr_l12l2/config/L2_format.yaml')
        conf_nc = get_nc_format_config(nc_format_config_file)
        basename = os.path.join(self.conf['data']['output_dir'], self.conf['data']['output_file_prefix']
                                + self.wigos + '_' + self.inst_id)
        #TODO: at the moment use mwr_files for filename and not the actual retrieved period: TO CHANGE !
        filename = generate_output_filename(basename, 'instamp_max', self.mwr_files)
        nc_writer = Writer(data, filename, conf_nc)
        nc_writer.run()


if __name__ == '__main__':
    ret = Retrieval(abs_file_path('mwr_l12l2/config/retrieval_config.yaml'))
    ret.run(start_time=dt.datetime(2023, 4, 25, 13, 0, 0), end_time=dt.datetime(2023, 4, 25, 16, 0, 0))

    pass
