import os
import time
import glob

import boto3
import datetime as dt

from pathlib import Path
from queue import Queue

from mwr_l12l2.log import logger
from mwr_l12l2.utils.file_utils import create_batch, get_mwr_file_times


class S3Watcher:
    """Poll an S3 bucket for new MWR L1 files and queue them for retrieval.

    New objects in ``mwr_bucket`` (optionally filtered by ``mwr_bucket_prefix``)
    that match the ``mwr_file_prefix`` are downloaded to ``mwr_dir`` and then
    passed through the batch-building logic before being placed on *queue* for
    the retrieval worker.

    The batching logic mirrors
    https://github.com/MeteoSwiss/dl_toolbox_runner/blob/main/dl_toolbox_runner/retrieval_manager.py:
    each incoming file is assigned to a retrieval time window.  Once a batch window has ended *and*
    a configurable ``delay`` has passed, the batch is pushed to the queue.
    Batches that are never completed within ``max_batch_age`` minutes are
    discarded.

    Args:
        conf: retrieval configuration dictionary (already parsed)
        queue: :class:`queue.Queue` instance shared with the worker thread
        poll_interval: seconds between successive S3 bucket listings. Defaults to 30.
    """

    def __init__(self, conf, queue, poll_interval=30):
        self.conf = conf
        self.queue = queue
        self.poll_interval = poll_interval

        # Batching parameters – driven by the retrieval config where possible
        self.retrieval_time = conf['general'].get('retrieval_time', 15)  # minutes
        self.threshold = conf['data'].get('mwr_obs_duration_threshold', 0.6)
        self.max_batch_age = 120  # minutes
        self.delay = conf['data'].get('nrt_delay_minutes', 15)  # minutes delay before triggering retrieval

        self.retrieval_batches = []   # list of open batch dicts
        self._seen_keys = set()       # S3 object keys already processed (or intentionally skipped)

        # Build the S3 client once using the credentials file from the config
        creds = self._load_s3_credentials(conf['data']['bucket_credentials'])
        self.s3 = boto3.client(
            's3',
            endpoint_url=creds['endpoint'],
            aws_access_key_id=creds['access_key_id'],
            aws_secret_access_key=creds['secret_access_key'],
        )
        self.bucket = conf['data']['mwr_bucket']
        self.bucket_prefix = conf['data'].get('mwr_bucket_prefix', '')
        self.mwr_dir = conf['data']['mwr_dir']
        self.mwr_file_prefix = conf['data']['mwr_file_prefix']

        # Pre-populate _seen_keys with everything already in the bucket so that
        # only files that arrive *after* startup are downloaded and processed.
        self._snapshot_existing_keys()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self):
        """Start the polling loop (blocking). Call from a dedicated thread."""
        logger.info(f'S3Watcher started – polling s3://{self.bucket}/{self.bucket_prefix} '
                    f'every {self.poll_interval}s')
        while True:
            try:
                self._poll()
            except Exception as exc:
                logger.error(f'S3Watcher poll error: {exc}')
            time.sleep(self.poll_interval)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _snapshot_existing_keys(self):
        """Populate ``_seen_keys`` with all objects currently in the bucket.

        Called once at startup so that pre-existing files are never downloaded
        or queued for retrieval – only files arriving *after* this point are
        treated as new.
        """
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket, Prefix=self.bucket_prefix)
        count = 0
        for page in pages:
            for obj in page.get('Contents', []):
                self._seen_keys.add(obj['Key'])
                count += 1
        logger.info(f'S3Watcher: skipping {count} pre-existing objects in '
                    f's3://{self.bucket}/{self.bucket_prefix}')

    def _poll(self):
        """List the bucket and process any keys not yet seen."""
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket, Prefix=self.bucket_prefix)

        new_keys = []
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj['Key']
                filename = Path(key).name
                if key not in self._seen_keys and filename.startswith(self.mwr_file_prefix):
                    new_keys.append(key)

        for key in new_keys:
            self._seen_keys.add(key)
            local_path = self._download(key)
            if local_path is not None:
                self._on_new_file(local_path)

        # After processing new files, check existing batches for readiness
        for batch in list(self.retrieval_batches):
            self._check_and_process_batch(batch)

    def _download(self, key):
        """Download *key* from S3 to ``mwr_dir``. Returns local path or None on error."""
        os.makedirs(self.mwr_dir, exist_ok=True)
        local_path = os.path.join(self.mwr_dir, Path(key).name)
        try:
            self.s3.download_file(self.bucket, key, local_path)
            logger.info(f'Downloaded s3://{self.bucket}/{key} → {local_path}')
            return local_path
        except Exception as exc:
            logger.error(f'Failed to download s3://{self.bucket}/{key}: {exc}')
            return None

    def _on_new_file(self, filepath):
        """Parse a newly downloaded file and add it to the appropriate batch."""
        filename = Path(filepath).name

        # Extract wigos and inst_id from filename: MWR_1C01_<wigos>_<inst_id><date>.nc
        try:
            parts = filename.split('_')
            wigos = parts[2]
            inst_id = parts[3][0]
            wigos_and_id = f'{wigos}_{inst_id}'
        except (IndexError, ValueError):
            logger.error(f'Cannot parse wigos/inst_id from filename: {filename}')
            return

        file_start_time, file_end_time = get_mwr_file_times(filepath)
        if file_start_time is None:
            logger.error(f'Cannot read time from file: {filepath}')
            return

        file_length = (file_end_time - file_start_time).total_seconds()
        file_mid_time = file_start_time + dt.timedelta(seconds=file_length / 2)

        file_dict = {
            'file': filepath,
            'wigos_and_id': wigos_and_id,
            'file_start_time': file_start_time,
            'file_end_time': file_end_time,
            'file_length': file_length,
            'file_mid_time': file_mid_time,
        }

        logger.info(f'New file: {filename}  [{file_start_time} - {file_end_time}]')
        
        # Depending on the length of the file, different case needs to be handled:
        # 1. File is shorter than retrieval time: assign to batch or create new batch
        # 2. File is longer than retrieval time: split into multiple batches
        if file_length <= self.retrieval_time * 60:
            # Try to assign to an existing batch
            assigned = False
            for batch in self.retrieval_batches:
                if batch['wigos_and_id'] != wigos_and_id:
                    continue
                # File must overlap the batch's retrieval window
                if file_end_time <= batch['retrieval_start_time']:
                    continue
                if file_start_time >= batch['retrieval_end_time']:
                    continue

                # Fits in this window – add the file
                batch['files'].append(filepath)
                batch['batch_length_sec'] += file_length
                if file_start_time < batch['batch_start_time']:
                    batch['batch_start_time'] = file_start_time
                if file_end_time > batch['batch_end_time']:
                    batch['batch_end_time'] = file_end_time
                logger.info(f'Added {filename} to existing batch for {wigos_and_id} '
                            f'[{batch["retrieval_start_time"]} - {batch["retrieval_end_time"]}]')
                assigned = True
                break

            if not assigned:
                # Create a new batch for this file
                retrieval_start = file_start_time
                retrieval_end = retrieval_start + dt.timedelta(minutes=self.retrieval_time)
                batch = create_batch(file_dict, retrieval_start, retrieval_end)
                self.retrieval_batches.append(batch)
                logger.info(f'New batch for {wigos_and_id} '
                            f'[{retrieval_start} - {retrieval_end}]')
        else:
            # File is longer than retrieval time – split into multiple batches
            num_batches = int(file_length // (self.retrieval_time * 60)) + 1
            for i in range(num_batches):
                batch_start = file_start_time + dt.timedelta(minutes=i * self.retrieval_time)
                batch_end = batch_start + dt.timedelta(minutes=self.retrieval_time)
                if batch_start >= file_end_time:
                    break
                if batch_end > file_end_time:
                    batch_end = file_end_time

                batch_dict = {
                    'file': filepath,
                    'wigos_and_id': wigos_and_id,
                    'file_start_time': file_start_time,
                    'file_end_time': file_end_time,
                    'file_length': file_length,
                    'file_mid_time': file_mid_time,
                }
                batch = create_batch(batch_dict, batch_start, batch_end)
                self.retrieval_batches.append(batch)
                logger.info(f'Created batch {i+1}/{num_batches} for {wigos_and_id} '
                            f'[{batch_start} - {batch_end}]')

    def _check_and_process_batch(self, batch):
        """Decide whether a batch is ready to be queued for retrieval.

        A batch is queued when:

        * it contains enough data (``batch_length_sec ≥ threshold × retrieval_time``), AND
        * the retrieval window end has passed the configured *delay*.

        A batch is discarded when it is older than ``max_batch_age`` minutes.
        """
        now = dt.datetime.now()

        # Discard stale batches
        if batch['batch_creation_time'] < now - dt.timedelta(minutes=self.max_batch_age):
            logger.warning(f'Batch for {batch["wigos_and_id"]} is too old – discarding')
            self.retrieval_batches.remove(batch)
            return

        enough_data = batch['batch_length_sec'] >= self.threshold * self.retrieval_time * 60
        window_elapsed = batch['retrieval_end_time'] < now - dt.timedelta(minutes=self.delay)

        if enough_data and window_elapsed:
            self.queue.put(batch)
            self.retrieval_batches.remove(batch)
            logger.info(f'Queued batch for {batch["wigos_and_id"]} '
                        f'[{batch["retrieval_start_time"]} – {batch["retrieval_end_time"]}] '
                        f'(queue size: {self.queue.qsize()})')

    @staticmethod
    def _load_s3_credentials(credentials_file):
        """Parse an s3cfg-style credentials file.

        Returns:
            dict with keys ``access_key_id``, ``secret_access_key``, ``endpoint``
        """
        config = {}
        with open(credentials_file, 'r') as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    config[key.strip()] = value.strip()
        return {
            'access_key_id': config['access_key'],
            'secret_access_key': config['secret_key'],
            'endpoint': config['host_base'],
        }
