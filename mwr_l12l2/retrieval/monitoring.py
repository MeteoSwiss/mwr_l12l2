import os
import time
import glob

import datetime as dt
import matplotlib.pyplot as plt
from mwr_l12l2.errors import MissingDataError, MWRConfigError
from mwr_l12l2.log import logger
from mwr_l12l2.utils.config_utils import get_retrieval_config, get_inst_config
from mwr_l12l2.utils.file_utils import abs_file_path
from mwr_l12l2.utils.monitoring_utils import read_mwr_summary_csv, Level1, ObservationMinusBackground
from mwr_l12l2.retrieval.retrieval import Retrieval

class Level1Monitoring(object):
    """Class to monitor Level 1 data and create summary plots and statistics

    Args:
        conf: configuration file or dictionary
        l1_instrument_list: path to csv file containing list of instruments to monitor
    """

    def __init__(self, conf, l1_instrument_list):
        if isinstance(conf, dict):
            self.conf = conf
        elif os.path.isfile(conf):
            self.conf = get_retrieval_config(conf)
        else:
            logger.error("The argument 'conf' must be a conf dictionary or a path pointing to a config file")
            raise MWRConfigError("The argument 'conf' must be a conf dictionary or a path pointing to a config file")

        self.l1_instrument_list = read_mwr_summary_csv(l1_instrument_list)

        # # set by list_obs():
        self.mwr_files = None
        self.alc_files = None

    def set_instrument(self, wigos, inst_id):
        """set instrument and config file manually providing wigos and inst_id"""

        logger.info('Setting instrument to {} {}'.format(wigos, inst_id))

        # set wigos and station id
        self.wigos = wigos
        self.inst_id = inst_id

        # List files to check it some exist
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                                '{}*{}_{}*.nc'.format(self.conf['data']['mwr_file_prefix'],
                                                                      self.wigos, self.inst_id)))
        
        if not list_of_files:
            err_msg = 'No MWR data found in {}'.format(self.conf['data']['mwr_dir'])
            logger.error(err_msg)

        inst_conf_file = '{}{}_{}.yaml'.format(self.conf['data']['inst_config_file_prefix'],
                                               self.wigos, self.inst_id)
        self.inst_conf = get_inst_config(os.path.join(self.conf['data']['inst_config_dir'], inst_conf_file))
    
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
            logger.critical(err_msg)

    def compute_OmB_for_single_instrument(self, wigos, inst_id, start_time, end_time):
        """Compute OmB for a single instrument over a specified time range

        Args:
            wigos (str): WIGOS station identifier
            inst_id (str): Instrument identifier
            start_time (datetime): Start time for the OmB computation
            end_time (datetime): End time for the OmB computation
        """
        self.set_instrument(wigos, inst_id)
        self.list_obs_files()

        selected_instrument = {
            'wigos': self.wigos,
            'inst_id': self.inst_id,
            'inst_conf': self.inst_conf,
            'mwr_files': self.mwr_files,
            'alc_files': self.alc_files
        }

        if not self.mwr_files:
            logger.info(f'No MWR files found for {self.wigos} {self.inst_id}. Skipping.')
            return

        ret = Retrieval(self.conf, selected_instrument, node=1)
        ret.monitor(start_time, end_time, OmB=True)
        omb = ObservationMinusBackground(wigos=self.wigos, inst_id=self.inst_id,
                                        tropoe_OmB_file=ret.tropoe_omb_file,
                                        tropoe_output_config=abs_file_path('mwr_l12l2/config/tropoe_output_config.yaml'))
        omb.read_tropoe()
        omb.plot_omb(output_dir=self.conf['quicklook_outdir'])
    
    def monitor_mwr_l1(self, day=None, OmB=False, single_wigos=None, singe_inst_id=None):
        """Monitor MWR L1 data for instruments listed in the provided summary.

        Args:
            day (datetime.datetime, optional): reference day. Defaults to today.
            OmB (bool, optional): whether to perform O-B processing. Defaults to True.
            output_dir (str, optional): directory to write quicklook images. If None a 'monitoring/quicklooks'
                directory under the current working directory is used.
            wigos (str, optional): WIGOS station identifier to filter instruments. If provided, only this instrument is processed.
            inst_id (str, optional): Instrument identifier to filter instruments. If provided, only this instrument is processed.
        """
        if day is None:
            day = dt.datetime.today()

        # Check that output_dir exists 
        if not self.conf['quicklook_outdir']:
            raise MWRConfigError("The argument 'output_dir' must be provided and point to a valid directory")
        
        for index, inst in self.l1_instrument_list.iterrows():
            if single_wigos is not None and singe_inst_id is not None:
                if (inst['wigos_station_id'] != single_wigos) or (inst['instrument_id'] != singe_inst_id):
                    continue
                else:
                    logger.info(f'Processing only instrument {single_wigos} {singe_inst_id}')
            wigos = inst['wigos_station_id']
            inst_id = inst['instrument_id']
            start_time = day.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=1)
            end_time = day.replace(hour=23, minute=59, second=0, microsecond=0) - dt.timedelta(days=1)
            datetime_str = start_time.strftime('%Y%m%d')

            try:
                # prepare instrument context and file lists
                self.set_instrument(wigos, inst_id)
                self.list_obs_files()

                selected_instrument = {
                    'wigos': self.wigos,
                    'inst_id': self.inst_id,
                    'inst_conf': self.inst_conf,
                    'mwr_files': self.mwr_files,
                    'alc_files': self.alc_files
                }

                if not self.mwr_files:
                    logger.info(f'No MWR files found for {self.wigos} {self.inst_id}. Skipping.')
                    # Save an empty figure to indicate no data
                    base_filename = f"L1_{self.wigos}_{self.inst_id}_{datetime_str}"
                    fig = plt.figure(figsize=(10, 6))
                    plt.text(0.5, 0.5, 'No MWR data available for ' + self.wigos + self.inst_id,
                             horizontalalignment='center', verticalalignment='center', fontsize=20)
                    plt.axis('off')
                    filename = os.path.join(self.conf['quicklook_outdir'], f"{base_filename}_zenith.jpg")
                    fig.savefig(filename, format='jpg', dpi=300, bbox_inches='tight')
                    plt.close(fig)
                    continue

                # run retrieval/monitor for this instrument
                ret = Retrieval(self.conf, selected_instrument, node=1)
                ret.monitor(start_time, end_time, OmB)
                quicklook = Level1(self.conf['quicklook_outdir'])
                quicklook.plot_l1(ret.mwr, date_start=None, date_stop=None, plot_tb=True, plot_scan=False, plot_housekeeping=True, plot_meteo=True, plot_tb_spectra=True)
                omb = ObservationMinusBackground(wigos=self.wigos, inst_id=self.inst_id,
                                    tropoe_OmB_file=ret.tropoe_omb_file,
                                    tropoe_output_config=abs_file_path('mwr_l12l2/config/tropoe_output_config.yaml'))
                omb.read_tropoe()
                omb.plot_omb(output_dir=self.conf['quicklook_outdir'])
            except Exception as e:
                logger.error(f"Error processing {wigos} {inst_id}: {e}")
                continue
                

if __name__ == '__main__':
    inst = Level1Monitoring(abs_file_path('mwr_l12l2/config/omb_config.yaml'),
                            l1_instrument_list='/home/eric/eprofile_config/mwr/mwr_raw2l1_summary.csv')
    # For quick testing limit instruments: pass max_instruments=5
    inst.monitor_mwr_l1(OmB=True) #, single_wigos='0-276-13-20039', singe_inst_id='A')
    # day=dt.datetime.today()
    pass
