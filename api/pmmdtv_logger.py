"""
Provides webhook call for Plex-Meta-Manager, to create DizqueTV channels
"""

# pylint: disable=E0401
# pylint: disable=R0912
# pylint: disable=R0914
# pylint: disable=R0915

import logging

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "logging.Formatter",
            "fmt": "{asctime} - {levelname:<6s} | {message}",
            "style": "{"
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "": {"handlers": ["default"]},
    },
}

def get_config():
    """
    Get the default logger config
    """
    return LOGGING_CONFIG

def get_logger():
    """
    Get the logger
    """
    # get the LOGGER, we wll use the uvicorn LOGGER to make format consistent
    logger = logging.getLogger("default")
    return logger
