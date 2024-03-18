"""Defines manifester's internal logging."""
import logging
from pathlib import Path

import logzero


def setup_logzero(level="info", path="logs/manifester.log", silent=True):
    """Call logzero setup with the given settings."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    log_fmt = "%(color)s[%(levelname)s %(asctime)s]%(end_color)s %(message)s"
    debug_fmt = (
        "%(color)s[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d]%(end_color)s %(message)s"
    )
    log_level = getattr(logging, level.upper(), logging.INFO)
    # formatter for terminal
    formatter = logzero.LogFormatter(fmt=debug_fmt if log_level is logging.DEBUG else log_fmt)
    logzero.setup_logger(formatter=formatter, disableStderrLogger=silent)
    logzero.loglevel(log_level)
    # formatter for file
    formatter = logzero.LogFormatter(
        fmt=debug_fmt if log_level is logging.DEBUG else log_fmt, color=False
    )
    logzero.logfile(path, loglevel=log_level, maxBytes=1e9, backupCount=3, formatter=formatter)
