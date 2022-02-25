"""
Provides webook call for Plex-Meta-Manager, to create DizqueTV channels
"""

# pylint: disable=E0401
# pylint: disable=R0912
# pylint: disable=R0914
# pylint: disable=R0915

import logging
import yaml

import pmmdtv_logger

def get_config():
    """
    Get the configuration from the config file
    """
    logger = pmmdtv_logger.get_logger()
    with open("/config/config.yml", "r") as config_file:
        config = yaml.load(config_file, Loader=yaml.SafeLoader)
        if 'debug' in config['dizquetv'] and config['dizquetv']['debug']:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    return config

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
    return "%s - %s" % (col_section, col_name)

def get_channel_group(col_section: str, col_name: str):
    """ Gets the channel group """
    config = get_collection_config(col_section, col_name)

    # Look for name setting in specific Channel
    if 'channel_group' in config:
        return config['channel_group']

    # nothing was found
    return None

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

    # Not found, look for default fillers setting
    if 'libraries' in config and \
        col_section in config['libraries'] and \
        col_name in config['libraries'][col_section]:
        collection_config = config['libraries'][col_section][col_name]

    if not collection_config:
        collection_config = {}

    default_config.update(collection_config)

    return default_config
