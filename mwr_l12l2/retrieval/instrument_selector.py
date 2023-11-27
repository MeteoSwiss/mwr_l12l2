import os
import sys
import time
import logging
import argparse
import glob

import multiprocessing as mp

import datetime as dt
import numpy as np

from mwr_l12l2.errors import MissingDataError, MWRConfigError, MWRInputError
from mwr_l12l2.log import logger
from mwr_l12l2.utils.config_utils import get_retrieval_config, get_inst_config
from retrieval import Retrieval

# from watchdog.observers import Observer
# from watchdog.events import LoggingEventHandler


class InstrumentSelector(object):
    """Class that select and the instrument and list the files needed for the retrieval
    It is now done outside of the retrieval class to prepare for parallel retrievals.

    Essentially just running the original method "select_instrument" and "list_obs_files" from the retrieval class.

    Args:
        conf: configuration file or dictionary
    """

    def __init__(self, conf):
        if isinstance(conf, dict):
            self.conf = conf
        elif os.path.isfile(conf):
            self.conf = get_retrieval_config(conf)
        else:
            logger.error("The argument 'conf' must be a conf dictionary or a path pointing to a config file")
            raise MWRConfigError("The argument 'conf' must be a conf dictionary or a path pointing to a config file")

        # set by select_instrument():
        self.wigos = None
        self.inst_id = None
        self.inst_conf = None

        # set by list_obs():
        self.mwr_files = None
        self.alc_files = None

    def select_oldest(self):
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
        #self.wigos = '0-20008-0-INO'
        
        self.inst_id = oldest_file.split('/')[-1].split('_')[3][0]
        #self.inst_id = 'A'

        inst_conf_file = '{}{}_{}.yaml'.format(self.conf['data']['inst_config_file_prefix'],
                                               self.wigos, self.inst_id)
        self.inst_conf = get_inst_config(os.path.join(self.conf['data']['inst_config_dir'], inst_conf_file))

    def set_instrument(self, wigos, inst_id):
        """set instrument and config file manually providing wigos and inst_id"""
        # TODO: implement this
        # TODO: Need to lock lookup for station selection for other nodes until prepare_eprofile_main with delete_mwr_in
        #       is done. Something like https://stackoverflow.com/questions/52815858/python-lock-directory might work.
        #       but better use ecflow to not data listing for other nodes until end of prepare_eprofile_main

        # set wigos and station id
        self.wigos = wigos
        self.inst_id = inst_id

        # List files to check it some exist
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                                '{}*{}_{}*.nc'.format(self.conf['data']['mwr_file_prefix'],
                                                                      self.wigos, self.inst_id)))
        
        if not list_of_files:
            logger.error('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
            raise MissingDataError('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))

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
            # TODO: also add a CRITICAL entry with err_msg to logger before raising the exception
            raise MissingDataError(err_msg)

    def retrieve_single(self, start_time, end_time, wigos=None, inst_id=None):
        """Method to run the retrieval for a single instrument (oldest found in the retrieval folder)

        Args:
            start_time (optional): earliest time from which to consider data. If not specified, all data younger than
                'max_age' specified in retrieval config will be used or, if 'max_age' is None, age of data is unlimited.
            end_time (optional): latest time from which to consider data. If not specified, all data received by now is
                processed.
        """
        if wigos is not None and inst_id is not None:
            self.set_instrument(wigos, inst_id)
        else:
            self.select_oldest()
        self.list_obs_files()

        # Necessary information to perform the retrieval for the selected instrument
        selected_instrument = {
            'wigos': self.wigos,
            'inst_id': self.inst_id,
            'inst_conf': self.inst_conf,
            'mwr_files': self.mwr_files,
            'alc_files': self.alc_files
        }

        ret = Retrieval(self.conf, selected_instrument, node=1)
        ret.run(start_time, end_time)

if __name__ == '__main__':
    start = time.time()
    instrument = InstrumentSelector('/home/sae/Documents/MWR/retrieval_config_VM_ES.yaml')
    instrument.retrieve_single(start_time=dt.datetime(2023, 10, 23, 0, 0, 0),  end_time=dt.datetime(2023, 10, 23, 23, 59, 0), wigos='0-20000-0-06610', inst_id = 'A')
    end = time.time()
    print('Time taken to run the retrieval: {} seconds'.format(end-start))

    pass





