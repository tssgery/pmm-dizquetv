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

    set_collection_defaults(col_section + " - " + col_name, default_config)

    return default_config

def set_collection_defaults(channel_name: str, settings: dict):
    """ takes a collection/channel config and makes sure default values are set """
    if 'ignore' not in settings:
        settings['ignore'] = False

    if 'pad' not in settings:
        settings['pad'] = 0

    if 'channel_group' not in settings:
        settings['channel_group'] = None

    if 'minimum_days' not in settings:
        settings['minimum_days'] = 0

    if 'fillers' not in settings:
        settings['fillers'] = []

    if 'random' not in settings:
        settings['random'] = True

    if 'channel_name' not in settings:
        settings['channel_name'] = channel_name
