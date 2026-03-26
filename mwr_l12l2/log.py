import datetime as dt
import os
from logging import DEBUG, Formatter, StreamHandler, getLogger
from logging.handlers import TimedRotatingFileHandler
from sys import stdout

from mwr_l12l2.utils.config_utils import get_log_config
from mwr_l12l2.utils.file_utils import abs_file_path


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
    today_str = dt.datetime.now(tz=dt.timezone(dt.timedelta(0))).strftime('%Y%m%d')
    log_filename = conf['logfile_basename'] + today_str + conf['logfile_ext']
    log_file = str(abs_file_path(os.path.join(conf['logfile_path'], log_filename)))

    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',       # rotate at midnight
        utc=True,              # use UTC for rotation timing
        backupCount=conf.get('logfile_backup_count', 30),  # keep N days of history
    )
    # The rotated files get a '.YYYY-MM-DD' suffix appended automatically
    file_handler.setFormatter(formatter)
    file_handler.setLevel(conf['loglevel_file'])
    logger.addHandler(file_handler)
