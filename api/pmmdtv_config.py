"""
Provides webhook call for Plex-Meta-Manager, to create DizqueTV channels
"""

# pylint: disable=import-error
# pylint: disable=too-many-branches

import logging
from schema import Optional, Schema, SchemaError
import yaml

import pmmdtv_logger

# configuration for plex schema
config_schema_plex = Schema({
    "url": str,
    "token": str,
})

# configuration for dizquetv schema
config_schema_dizquetv = Schema({
    "url": str,
    Optional("debug"): bool,
    Optional("discord"): {
        Optional("url"): str,
        Optional("username"): str,
        Optional("avatar"): str,
    },
})

# configuration for library defaults section
config_schema_defaults = Schema({
    Optional("pad"): int,
    Optional("fillers"): list,
    Optional("channel_group"): str,
    Optional("minimum_days"): int,
    Optional("random"): bool,
    Optional("dizquetv_start"): int,
})

# configuration for channels section
config_schema_channel = Schema({
    Optional("pad"): int,
    Optional("fillers"): list,
    Optional("channel_group"): str,
    Optional("minimum_days"): int,
    Optional("channel_name"): str,
    Optional("random"): bool,
})

def get_config(validate: bool = False):
    """
    Get the configuration from the config file
    """
    logger = pmmdtv_logger.get_logger()
    with open("/config/config.yml", "r", encoding="utf-8") as config_file:
        config = yaml.load(config_file, Loader=yaml.SafeLoader)
        if 'debug' in config['dizquetv'] and config['dizquetv']['debug']:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    if validate:
        validate_config(config)

    return config

def validate_defaults_config(config, col_section):
    """
    Validate the configuration against a schema
    """
    logger = pmmdtv_logger.get_logger()
    # validate 'defaults' schema
    try:
        config_schema_defaults.validate(config)
    except SchemaError as schema_error:
        for error in schema_error.autos:
            logger.warning("Within defaults for \"%s\": %s", col_section, error)

def validate_channel_config(config, col_name):
    """
    Validate the configuration against a schema
    """
    logger = pmmdtv_logger.get_logger()
    # validate 'channel' schema
    try:
        config_schema_channel.validate(config)
    except SchemaError as schema_error:
        for error in schema_error.autos:
            logger.warning("Channel settings for \"%s\": %s", col_name, error)

def validate_config(config):
    """
    Validate the configuration against a schema
    """
    logger = pmmdtv_logger.get_logger()
    # validate 'plex' schema
    try:
        config_schema_plex.validate(config['plex'])
    except SchemaError as schema_error:
        for error in schema_error.autos:
            logger.warning("Within \"plex\" section: %s", error)

    # validate 'dizquetv' schema
    try:
        config_schema_dizquetv.validate(config['dizquetv'])
    except SchemaError as schema_error:
        for error in schema_error.autos:
            logger.warning("Within \"dizquetv\" section: %s", error)

    # validate 'defaults' schema
    if config['defaults']:
        for section in config['defaults']:
            validate_defaults_config(config=config['defaults'][section],
                col_section=section)

    # validate 'libraries' schema
    if config['libraries']:
        for section in config['libraries']:
            for channel in config['libraries'][section]:
                validate_channel_config(config=config['defaults'][section],
                    col_name=channel)

def get_pad_time(col_section: str, col_name: str):
    """ Gets the padding time for the channel """
    config = get_collection_config(col_section, col_name)

    # Look for pad setting
    if 'pad' in config:
        return config['pad']

    # nothing was found
    return None


def get_filler_lists(col_section: str, col_name: str):
    """ Gets the names of the filler lists """
    config = get_collection_config(col_section, col_name)

    # Look for fillers setting in specific Channel
    if 'fillers' in config:
        return config['fillers']

    # nothing was found
    return []


def get_random(col_section: str, col_name: str, default: bool = True):
    """ Gets the randomize setting """
    config = get_collection_config(col_section, col_name)

    # Look for fillers setting in specific Channel
    if 'random' in config:
        return config['random']

    # nothing was found
    return default


def get_minimum_days(col_section: str, col_name: str, default: int = 0):
    """ Gets the randomize setting """
    config = get_collection_config(col_section, col_name)

    # Look for minimum_days setting in specific Channel
    if 'minimum_days' in config:
        return config['minimum_days']

    # nothing was found
    return default


def get_channel_name(col_section: str, col_name: str):
    """ Gets the channel name """
    config = get_collection_config(col_section, col_name)

    # Look for name setting in specific Channel
    if 'channel_name' in config:
        return config['channel_name']

    # nothing was found
    return f"{col_section} - {col_name}"


def get_channel_group(col_section: str, col_name: str):
    """ Gets the channel group """
    config = get_collection_config(col_section, col_name)

    # Look for name setting in specific Channel
    if 'channel_group' in config:
        return config['channel_group']

    # nothing was found
    return None


def get_ignore_channel(col_section: str, col_name: str) -> bool:
    """ Gets the ignore channel setting """
    config = get_collection_config(col_section, col_name)

    # Look for ignore setting in specific Channel
    if 'ignore' in config:
        return config['ignore']

    # nothing was found
    return False


def get_collection_config(col_section: str, col_name: str):
    """ Gets the configuration for a specific collection """
    config = get_config()
    default_config = {}
    collection_config = {}

    # Look for default values
    if 'defaults' in config and \
            col_section in config['defaults']:
        default_config = config['defaults'][col_section]

    if not default_config:
        default_config = {}

    # validate default settings
    validate_defaults_config(config=default_config, col_section=col_section)

    # Not found, look for default fillers setting
    if 'libraries' in config and \
            col_section in config['libraries'] and \
            col_name in config['libraries'][col_section]:
        collection_config = config['libraries'][col_section][col_name]

    if not collection_config:
        collection_config = {}

    # validate collection schema
    validate_channel_config(config=collection_config, col_name=col_name)

    default_config.update(collection_config)

    return default_config
