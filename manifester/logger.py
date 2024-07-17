"""Defines manifester's internal logging."""

import logging
from pathlib import Path

from dynaconf import Dynaconf
import logzero

from manifester._settings import settings_path

# Initialize temporary settings without running the Vault loader
temp_settings = Dynaconf(
    settings_file=str(settings_path.absolute()),
    ENVVAR_PREFIX_FOR_DYNACONF="MANIFESTER",
    load_dotenv=False,
)


def _setup_logzero(
    level=temp_settings.get("log_level", "info"),
    path="logs/manifester.log",
    name=None,
    formatter=None,
    silent=True,
):
    """Call logzero setup with the given settings."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    log_fmt = "%(color)s[%(levelname)s %(asctime)s]%(end_color)s %(message)s"
    debug_fmt = (
        "%(color)s[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d]%(end_color)s %(message)s"
    )
    log_level = getattr(logging, level.upper(), logging.INFO)
    # formatter for terminal
    formatter = logzero.LogFormatter(fmt=debug_fmt if log_level is logging.DEBUG else log_fmt)
    if not name:
        name = "manifester"
    # formatter for file
    formatter = logzero.LogFormatter(
        fmt=debug_fmt if log_level is logging.DEBUG else log_fmt, color=False
    )
    logger = logzero.setup_logger(
        name=name,
        formatter=formatter,
        level=log_level,
        logfile=path,
        maxBytes=1e9,
        backupCount=3,
        disableStderrLogger=silent,
    )
    return logger


_logger = _setup_logzero()
# delete temporary settings after initializing the logger
del temp_settings


def setup_logzero(level, path, name=None, silent=True):
    """Call logzero setup with the given settings."""
    _logger = _setup_logzero(level, path, name, silent)
