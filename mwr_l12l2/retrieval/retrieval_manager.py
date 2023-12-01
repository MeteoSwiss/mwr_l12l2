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
from mwr_l12l2.utils.config_utils import abs_file_path, get_retrieval_config, get_inst_config
from retrieval import Retrieval

# from watchdog.observers import Observer
# from watchdog.events import LoggingEventHandler

class RetrievalManager(object):
    """Class to manage the operational retrieval of MWR data from E-PROFILE

    In essence, the idea is to check available files in a retrieval folder and run a retrieval for each station
    Now also with multiprocessing capabilities (50% speedup on 4 cores)

    Args:
        conf: configuration file or dictionary
    """
    def __init__(self, conf):
        if isinstance(conf, dict):
            self.conf = conf
        elif os.path.isfile(conf):
            self.conf = get_retrieval_config(conf)
        else:
            raise MWRConfigError("The argument 'conf' must be a conf dictionary or a path pointing to a config file")

        self.wigos_list = []
        self.wigos_and_inst_id_list = []
        self.wigos_and_inst_id_unique = []
        self.mwr_files_dict = {}
        self.alc_files_dict = {}
        self.retrieval_dict = {}
        self.inst_conf = {}

    def select_all_instruments(self):
        """select all instruments which have mwr files in input dir.

        Sets dictionaries for MWR and ALC with all the instruments filenames present in the folder.
        """
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                               '{}*.nc'.format(self.conf['data']['mwr_file_prefix'])))
        
        if not list_of_files:
            raise MissingDataError('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
        
        # get station id from filenames
        for filename in list_of_files:
            self.wigos_list.append(filename.split('/')[-1].split('_')[2])
            self.wigos_and_inst_id_list.append(filename.split('/')[-1].split('_')[2]+'_'+filename.split('/')[-1].split('_')[3][0])
        
        # identify unique wigos and instr_id combination
        self.wigos_and_inst_id_unique = list(set(self.wigos_and_inst_id_list))

        # split filenames per wigos and put in a dictionary:
        # TODO: add a filter to only list filenames between start and end time of retrieval 
        # Otherwise these files will get deleted and not retrieved
        mwr_files_dict = {}
        for wigos_and_id in self.wigos_and_inst_id_unique:
            mwr_files_dict[wigos_and_id] = []
            for filenames in list_of_files:
                if wigos_and_id in filenames:
                    mwr_files_dict[wigos_and_id].append(filenames)
            
        self.mwr_files_dict = mwr_files_dict

        # get alc files for each identified MWR
        alc_files_dict = {}
        for wigos_and_id in self.wigos_and_inst_id_unique:
            alc_files_dict[wigos_and_id] = []
            for filenames in glob.glob(os.path.join(self.conf['data']['alc_dir'],
                                                    '{}*{}*.nc'.format(self.conf['data']['alc_file_prefix'],
                                                                       wigos_and_id.split('_')[0]))):
                alc_files_dict[wigos_and_id].append(filenames)

        self.alc_files_dict = alc_files_dict

    def prepare_retrieval_dicts(self):
        """Method to prepare the dictionarie for the retrieval

        For now, it only create a dictionary for the instrument where a config file exist.

        """
        # prepare the dictionaries for the retrieval
        for wigos_and_id in self.wigos_and_inst_id_unique:
            # Try to read the config file first and only add it to the list if config is found
            try:
                inst_conf_file = '{}{}_{}.yaml'.format(self.conf['data']['inst_config_file_prefix'],
                                                       wigos_and_id.split('_')[0], wigos_and_id.split('_')[1])
                self.inst_conf = get_inst_config(os.path.join(self.conf['data']['inst_config_dir'], inst_conf_file))
                self.retrieval_dict[wigos_and_id] = {
                    'wigos': wigos_and_id.split('_')[0],
                    'inst_id': wigos_and_id.split('_')[1],
                    'inst_conf': self.inst_conf,
                    'mwr_files': self.mwr_files_dict[wigos_and_id],
                    'alc_files': self.alc_files_dict[wigos_and_id]
                }
            except:
                print('Instrument config file not found for {}_{}'.format(wigos_and_id.split('_')[0],
                                                                          wigos_and_id.split('_')[1]))
                continue

    def run_retrieval(self, start_time, end_time, selected, node=None):
        """Perform retrieval for a single instrument using a dictionary with all relevant instrument information
        
        Args:
            selected (dict): dictionary with the information for the retrieval
            start_time (optional): earliest time from which to consider data. If not specified, all data younger than
                'max_age' specified in retrieval config will be used or, if 'max_age' is None, age of data is unlimited.
            end_time (optional): latest time from which to consider data. If not specified, all data received by now is
                processed.
            node (optional): node number to be used for the retrieval. If not specified, node 0 is used.
        """
        ret = Retrieval(self.conf, selected, node)
        ret.run(start_time, end_time)

    def retrieve_all(self, start_time, end_time):
        """Perform the retrieval for all the instrument found in the folder. 
        At the moment we perform the retrievals one after the other.

        """
        self.select_all_instruments()
        self.prepare_retrieval_dicts()

        for (node_number, wigos_and_id) in enumerate(self.retrieval_dict):
            try:
                self.run_retrieval(start_time, end_time, self.retrieval_dict[wigos_and_id], node=node_number)
            except Exception as e:
                print(f"Retrieval for {wigos_and_id} failed with error: {e}")

    def retrieve_all_in_parallel(self, start_time, end_time, cores=2):
        """Use multiprocessing to run the retrieval in parallel. 
        """
        self.select_all_instruments()
        self.prepare_retrieval_dicts()

        # Create a pool of workers equal using 2 cores
        pool = mp.Pool(processes=cores)
        
        # Perform the retrieval in parallel.
        # warning: we need to loop into the dictionary itself and NOT on the self.wigos_and_inst_id_unique to avoid
        #          including instrument without config file
        results = [pool.apply_async(self.run_retrieval,
                                    args=(start_time, end_time, self.retrieval_dict[wigos_and_id], 10*(1+node_number))
                                    ) for (node_number, wigos_and_id) in enumerate(self.retrieval_dict)]

        output = []
        for p in results:
            try:
                output.append(p.get())
            except Exception as e:
                print(f"A process failed with error: {e}")
        # handle the error as appropriate for your program

        # Close the pool
        pool.close()

    def move_to_bucket(self):
        """Move the files to the bucket
        Execute this function when retrieval is successful (as argument of apply_async)
        """
        pass


if __name__ == '__main__':
    start = time.time()
    run_parallel = True
    manager = RetrievalManager(abs_file_path('mwr_l12l2/config/retrieval_config.yaml'))
    
    if run_parallel:
        manager.retrieve_all_in_parallel(start_time=dt.datetime(2023, 4, 25, 13, 0, 0), end_time=dt.datetime(2023, 4, 25, 16, 0, 0), cores=4)
    else:
        manager.retrieve_all(start_time=dt.datetime(2023, 4, 25, 13, 0, 0), end_time=dt.datetime(2023, 4, 25, 16, 0, 0))

    end = time.time()
    print('Time taken to run the retrievals: {} seconds'.format(end-start))

    pass





