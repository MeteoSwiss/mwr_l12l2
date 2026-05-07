import datetime as dt
import os
from logging import DEBUG, Formatter, StreamHandler, getLogger
from logging.handlers import BaseRotatingHandler
from sys import stdout

from mwr_l12l2.utils.config_utils import get_log_config
from mwr_l12l2.utils.file_utils import abs_file_path


class DailyRotatingFileHandler(BaseRotatingHandler):
    """
    A file handler that rotates daily based on the current UTC date.
    
    Unlike TimedRotatingFileHandler, this handler checks on every emit()
    whether the date has changed and rotates immediately if needed.
    This ensures rotation happens even for long-running processes.
    """
    
    def __init__(self, log_dir, basename, ext, backupCount=30, encoding=None):
        self.log_dir = log_dir
        self.basename = basename
        self.ext = ext
        self.backupCount = backupCount
        
        # Track which date we're currently logging to
        self._current_date = self._get_utc_date()
        
        # Build the initial filename
        filename = self._build_filename(self._current_date)
        os.makedirs(log_dir, exist_ok=True)
        
        super().__init__(filename, mode='a', encoding=encoding)
    
    def _get_utc_date(self):
        """Return current UTC date as YYYYMMDD string."""
        return dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')
    
    def _build_filename(self, date_str):
        """Build full path for log file with given date."""
        return os.path.join(self.log_dir, f"{self.basename}{date_str}{self.ext}")
    
    def shouldRollover(self, record):
        """Check if the UTC date has changed since last write."""
        current_date = self._get_utc_date()
        return current_date != self._current_date
    
    def doRollover(self):
        """Switch to a new log file for the current date."""
        # Close current stream
        if self.stream:
            self.stream.close()
            self.stream = None
        
        # Update to new date and filename
        self._current_date = self._get_utc_date()
        self.baseFilename = self._build_filename(self._current_date)
        
        # Open new file
        self.stream = self._open()
        
        # Clean up old log files if backupCount is set
        if self.backupCount > 0:
            self._delete_old_files()
    
    def _delete_old_files(self):
        """Delete log files older than backupCount days."""
        try:
            cutoff_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=self.backupCount)
            cutoff_str = cutoff_date.strftime('%Y%m%d')
            
            for filename in os.listdir(self.log_dir):
                if filename.startswith(self.basename) and filename.endswith(self.ext):
                    # Extract date portion: log_YYYYMMDD.txt -> YYYYMMDD
                    date_part = filename[len(self.basename):-len(self.ext)] if self.ext else filename[len(self.basename):]
                    if len(date_part) == 8 and date_part.isdigit() and date_part < cutoff_str:
                        try:
                            os.remove(os.path.join(self.log_dir, filename))
                        except OSError:
                            pass
        except Exception:
            pass  # Don't let cleanup errors affect logging


# get logs config
log_config_file = abs_file_path('mwr_l12l2/config/log_config.yaml')
conf = get_log_config(log_config_file)


# Colors for the logs console output (Options see color_log-package)
LOG_COLORS = {
    'DEBUG': 'cyan',
    'INFO': 'green',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'red,bg_white'}

try:
    # TODO: solve bug with colorlog package
    import colorlog

    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s [%(process)d] '
        '%(levelname)-8s %(message)s',
        datefmt=None,
        reset=True,
        log_colors=LOG_COLORS,
        secondary_log_colors={},
        style='%',
    )
    get_logger = colorlog.getLogger

except Exception as e:  # noqa E841
    #   print(e)
    get_logger = getLogger
    formatter = Formatter(
        '%(asctime)s [%(process)d] '
        '%(levelname)-8s %(message)s',
        '%Y-%m-%d %H:%M:%S',
    )


# general settings
logger = get_logger(conf['logger_name'])
logger.setLevel(DEBUG)  # set to the lowest possible level, using handler-specific levels for output


# logging to stdout
console_handler = StreamHandler(stdout)
console_formatter = formatter
console_handler.setFormatter(console_formatter)
console_handler.setLevel(conf['loglevel_stdout'])
logger.addHandler(console_handler)


# logging to file (daily rotating – new file every day at midnight UTC)
if conf['write_logfile']:
    log_dir = str(abs_file_path(conf['logfile_path']))

    file_handler = DailyRotatingFileHandler(
        log_dir=log_dir,
        basename=conf['logfile_basename'],
        ext=conf['logfile_ext'],
        backupCount=conf.get('logfile_backup_count', 30),
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(conf['loglevel_file'])
    logger.addHandler(file_handler)
