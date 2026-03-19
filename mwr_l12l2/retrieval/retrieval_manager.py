import os
import time
import glob

import multiprocessing as mp
import datetime as dt

from threading import Thread
from queue import Queue
from multiprocessing import Pool

from mwr_l12l2.errors import MissingDataError, MWRConfigError
from mwr_l12l2.log import logger
from mwr_l12l2.utils.config_utils import abs_file_path, get_retrieval_config, get_inst_config
from mwr_l12l2.retrieval.retrieval import Retrieval
from mwr_l12l2.retrieval.s3_watcher import S3Watcher


# =============================================================================
# Queue worker and retrieval runner
# =============================================================================

def process_queue(queue, conf):
    """Worker function run in a dedicated daemon thread.

    Continuously drains *queue* and spawns a single-process
    :class:`multiprocessing.Pool` for each batch so that failures are isolated.

    Args:
        queue: :class:`queue.Queue` of batch dicts produced by :class:`S3Watcher`
        conf: retrieval configuration dictionary passed through to :func:`run_retrieval`
    """
    while True:
        if not queue.empty():
            batch = queue.get()
            pool = Pool(processes=1)
            pool.apply_async(run_retrieval, args=(conf, batch),
                             error_callback=lambda e: logger.critical(f'Retrieval process failed: {e}'))
            pool.close()
            # Do NOT join – let the process run in the background while we keep draining the queue
        else:
            time.sleep(1)


def run_retrieval(conf, batch):
    """Run the retrieval for a single batch.

    Designed to be called inside a subprocess so that crashes are isolated.

    Args:
        conf: retrieval configuration dictionary
        batch: batch dict as produced by :func:`~mwr_l12l2.utils.file_utils.create_batch`
    """
    wigos_and_id = batch['wigos_and_id']
    logger.info(f'Starting retrieval for {wigos_and_id} '
                f'[{batch["retrieval_start_time"]} – {batch["retrieval_end_time"]}]')
    try:
        wigos, inst_id = wigos_and_id.split('_', 1)
        inst_conf_file = '{}{}.yaml'.format(
            conf['data']['inst_config_file_prefix'],
            wigos_and_id.replace('_', '_', 1),  # keep original format wigos_instid
        )
        # Resolve the instrument config file: prefix + wigos + '_' + inst_id + '.yaml'
        inst_conf_filename = '{}{}_{}.yaml'.format(
            conf['data']['inst_config_file_prefix'], wigos, inst_id)
        inst_conf = get_inst_config(
            os.path.join(conf['data']['inst_config_dir'], inst_conf_filename))

        # Collect ALC files for the relevant time window
        alc_files = glob.glob(os.path.join(
            conf['data']['alc_dir'],
            '{}*{}*.nc'.format(conf['data']['alc_file_prefix'], wigos)))

        selected = {
            'wigos': wigos,
            'inst_id': inst_id,
            'inst_conf': inst_conf,
            'mwr_files': batch['files'],
            'alc_files': alc_files,
        }

        ret = Retrieval(conf, selected)
        ret.run(batch['retrieval_start_time'], batch['retrieval_end_time'])
        logger.info(f'Retrieval completed for {wigos_and_id}')

    except Exception as exc:
        logger.error(f'Retrieval failed for {wigos_and_id}: {exc}')
        raise


# =============================================================================
# Entry point for real-time mode
# =============================================================================

def start_s3_watcher(conf_path, poll_interval=30):
    """Start the real-time retrieval loop driven by S3 bucket polling.

    Launches an :class:`S3Watcher` in a daemon thread that continuously polls
    the configured input S3 bucket for new MWR L1 files and a second daemon
    thread (:func:`process_queue`) that consumes the queue and runs retrievals
    in isolated sub-processes.

    Args:
        conf_path: path to the retrieval configuration YAML file
        poll_interval: seconds between S3 bucket polls. Defaults to 30.
    """
    conf = get_retrieval_config(conf_path)

    logger.info(f'Starting real-time S3 watcher – input bucket: {conf["data"]["mwr_bucket"]}')

    retrieval_queue = Queue()

    watcher = S3Watcher(conf, retrieval_queue, poll_interval=poll_interval)

    watcher_thread = Thread(target=watcher.run, daemon=True, name='S3WatcherThread')
    worker_thread = Thread(target=process_queue, args=(retrieval_queue, conf),
                           daemon=True, name='RetrievalWorkerThread')

    watcher_thread.start()
    worker_thread.start()

    logger.info('Real-time retrieval manager running. Press Ctrl+C to stop.')
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info('Shutdown requested – stopping real-time retrieval manager.')


# =============================================================================
# Batch / historical retrieval manager (kept for reprocessing use-cases)
# =============================================================================

class RetrievalManager:
    """Manage batch or historical retrieval of MWR data from E-PROFILE.

    Scans a local directory for MWR files and runs a retrieval for each
    station, optionally in parallel.

    Args:
        conf: configuration file path or already-parsed configuration dictionary
    """

    def __init__(self, conf):
        if isinstance(conf, dict):
            self.conf = conf
        elif os.path.isfile(conf):
            self.conf = get_retrieval_config(conf)
        else:
            logger.error("The argument 'conf' must be a conf dictionary or a path pointing to a config file")
            raise MWRConfigError("The argument 'conf' must be a conf dictionary or a path pointing to a config file")

        self.wigos_list = []
        self.wigos_and_inst_id_list = []
        self.wigos_and_inst_id_unique = []
        self.mwr_files_dict = {}
        self.alc_files_dict = {}
        self.retrieval_dict = {}
        self.inst_conf = {}

    def select_all_instruments(self):
        """Scan ``mwr_dir`` and build per-instrument file dictionaries.

        Sets :attr:`mwr_files_dict` and :attr:`alc_files_dict` keyed by
        ``<wigos>_<inst_id>``.
        """
        list_of_files = glob.glob(os.path.join(self.conf['data']['mwr_dir'],
                                               '{}*.nc'.format(self.conf['data']['mwr_file_prefix'])))

        if not list_of_files:
            logger.error('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))
            raise MissingDataError('No MWR data found in {}'.format(self.conf['data']['mwr_dir']))

        # get station id from filenames
        for filename in list_of_files:
            self.wigos_list.append(filename.split('/')[-1].split('_')[2])
            self.wigos_and_inst_id_list.append(
                filename.split('/')[-1].split('_')[2] + '_' + filename.split('/')[-1].split('_')[3][0])

        # identify unique wigos and instr_id combination
        self.wigos_and_inst_id_unique = list(set(self.wigos_and_inst_id_list))

        # split filenames per wigos and put in a dictionary
        mwr_files_dict = {}
        for wigos_and_id in self.wigos_and_inst_id_unique:
            mwr_files_dict[wigos_and_id] = [f for f in list_of_files if wigos_and_id in f]
        self.mwr_files_dict = mwr_files_dict

        # get alc files for each identified MWR
        alc_files_dict = {}
        for wigos_and_id in self.wigos_and_inst_id_unique:
            alc_files_dict[wigos_and_id] = glob.glob(
                os.path.join(self.conf['data']['alc_dir'],
                             '{}*{}*.nc'.format(self.conf['data']['alc_file_prefix'],
                                               wigos_and_id.split('_')[0])))
        self.alc_files_dict = alc_files_dict

    def prepare_retrieval_dicts(self):
        """Build :attr:`retrieval_dict` for instruments that have a config file."""
        for wigos_and_id in self.wigos_and_inst_id_unique:
            try:
                inst_conf_file = '{}{}_{}.yaml'.format(
                    self.conf['data']['inst_config_file_prefix'],
                    wigos_and_id.split('_')[0], wigos_and_id.split('_')[1])
                self.inst_conf = get_inst_config(
                    os.path.join(self.conf['data']['inst_config_dir'], inst_conf_file))
                self.retrieval_dict[wigos_and_id] = {
                    'wigos': wigos_and_id.split('_')[0],
                    'inst_id': wigos_and_id.split('_')[1],
                    'inst_conf': self.inst_conf,
                    'mwr_files': self.mwr_files_dict[wigos_and_id],
                    'alc_files': self.alc_files_dict[wigos_and_id],
                }
            except Exception:
                logger.error('Instrument config file not found for {}_{}'.format(
                    wigos_and_id.split('_')[0], wigos_and_id.split('_')[1]))
                continue

    def run_retrieval(self, start_time, end_time, selected, node=None):
        """Run a retrieval for a single instrument.

        Args:
            start_time: earliest time to consider (or ``None`` to rely on ``max_age``)
            end_time: latest time to consider (or ``None`` for up to now)
            selected: instrument dict as produced by :meth:`prepare_retrieval_dicts`
            node: TROPoe node number. Defaults to ``None`` (→ 0).
        """
        ret = Retrieval(self.conf, selected, node)
        ret.run(start_time, end_time)

    def retrieve_all(self, start_time, end_time):
        """Run retrievals for all instruments sequentially."""
        self.select_all_instruments()
        self.prepare_retrieval_dicts()

        for (node_number, wigos_and_id) in enumerate(self.retrieval_dict):
            try:
                self.run_retrieval(start_time, end_time,
                                   self.retrieval_dict[wigos_and_id], node=node_number)
            except Exception as e:
                logger.error(f'Retrieval for {wigos_and_id} failed with error: {e}')

    def retrieve_all_in_parallel(self, start_time, end_time, cores=2):
        """Run retrievals for all instruments in parallel using multiprocessing."""
        logger.info('Starting batch retrievals in multiprocessing')
        self.select_all_instruments()
        self.prepare_retrieval_dicts()

        pool = mp.Pool(processes=cores)
        results = [
            pool.apply_async(
                self.run_retrieval,
                args=(start_time, end_time,
                      self.retrieval_dict[wigos_and_id],
                      10 * (1 + node_number)))
            for (node_number, wigos_and_id) in enumerate(self.retrieval_dict)
        ]

        for p in results:
            try:
                p.get()
            except Exception as e:
                logger.critical(f'A process failed with error: {e}')

        pool.close()


# =============================================================================
# __main__
# =============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='MWR L1→L2 retrieval manager')
    parser.add_argument('--mode', choices=['realtime', 'batch'], default='realtime',
                        help='realtime: poll S3 bucket for new files; batch: process all files in mwr_dir')
    parser.add_argument('--config', default='mwr_l12l2/config/retrieval_config_ewc.yaml',
                        help='Path to retrieval configuration YAML (relative to project root or absolute)')
    parser.add_argument('--poll-interval', type=int, default=30,
                        help='Seconds between S3 polls (realtime mode only)')
    parser.add_argument('--cores', type=int, default=2,
                        help='Number of parallel processes (batch mode only)')
    args = parser.parse_args()

    conf_path = abs_file_path(args.config)

    if args.mode == 'realtime':
        start_s3_watcher(conf_path, poll_interval=args.poll_interval)
    else:
        start = time.time()
        manager = RetrievalManager(conf_path)
        manager.retrieve_all_in_parallel(start_time=None, end_time=None, cores=args.cores)
        logger.info('Batch retrievals finished in {:.1f} s'.format(time.time() - start))





