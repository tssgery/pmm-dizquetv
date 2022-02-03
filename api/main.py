"""
Provides webook call for Plex-Meta-Manager, to create DizqueTV channels
"""

# pylint: disable=E0401

import logging
import sys
from typing import Optional
import yaml

from plexapi import server
from discordwebhook import Discord
from dizqueTV import API
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# get the LOGGER, we wll use the ivucorn LOGGER to make format consistent
LOGGER = logging.getLogger("uvicorn.error")

def get_config():
    """
    Get the configuration from the config file
    """
    with open("/config/config.yml", "r") as config_file:
        config = yaml.load(config_file, Loader=yaml.SafeLoader)
        if 'debug' in config['dizquetv'] and config['dizquetv']['debug']:
            LOGGER.setLevel(logging.DEBUG)
        else:
            LOGGER.setLevel(logging.INFO)

    return config

CONFIG = get_config()
LOGGER.info("Read configuration")
LOGGER.info("PLEX URL set to: %s", CONFIG['plex']['url'])
LOGGER.info("DizqueTV URL set to: %s", CONFIG['dizquetv']['url'])
if not CONFIG['plex']['token']:
    LOGGER.error("No PLEX Token is set")
    sys.exit(1)

# create the API
APP = FastAPI()

# allow calls from anywhere
APP.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

class Collection(BaseModel):        # pylint: disable=too-few-public-methods
    """
    Class to encapsulte the payload from Plex-Meta-Manager
    """
    server_name: Optional[str]
    library_name: Optional[str]
    collection: Optional[str]
    playlist: Optional[str]
    poster: Optional[str]
    poster_url: Optional[str]
    background: Optional[str]
    background_url: Optional[str]
    created: Optional[bool]
    deleted: Optional[bool]


@APP.post("/collection", status_code=200)
async def hook(collection: Collection):
    """The actual webook, /collection, which gets all collection updates"""

    config = get_config()

    # boolean as to if the channel needed to be created
    operation = "Updated"

    # make sure a collection name was provided
    if collection.collection is None:
        LOGGER.error("Null collection name was received")
        send_discord(config=config, message="ERROR: Null collection name was received")
        return Response(status_code=400)

    col_name = collection.collection
    col_section = collection.library_name

    # calculate the dizquetv channel name
    channel_name = get_channel_name(
        section=col_section,
        name=col_name)
    LOGGER.info("Channel name: %s", channel_name)

    # get the channel number, will return 0 if no channel exists
    channel = dtv_get_channel_number(config=config, name=channel_name)
    LOGGER.info("Channel number: %d", channel)

    # handle collection deletion
    if collection.deleted:
        LOGGER.debug("Deleting channel (name: %s, number: %s)", channel_name, channel)
        dtv_delete_channel(config=config, number=channel)
        send_discord(config=config,
                     message="Deleted DizqueTV channel (name: %s, number %d)" % \
                     (channel_name, channel))
        return Response(status_code=200)

    # if the channel does not exist and we were not asked to delete it
    if channel == 0 and not collection.deleted:
        start_at = 1
        if 'libraries' in config and \
           collection.library_name in config['libraries'] and \
           'dizquetv_start' in config['libraries'][collection.library_name]:
            start_at = config['libraries'][collection.library_name]['dizquetv_start']
        LOGGER.debug("Creating channel (name: %s, number: %s)", channel_name, channel)
        channel = dtv_create_new_channel(config=config, name=channel_name, start_at=start_at)
        operation = "Created"

    # determine if the channel contents should be randomized
    randomize = True
    if 'libraries' in config and \
        col_section in config['libraries'] and \
        col_name in config['libraries'][col_section] and \
        'random' in config['libraries'][col_section][col_name] and \
        not config['libraries'][col_section][col_name]['random']:
        randomize = False

    # now remove the existing content and reset it
    LOGGER.debug("Updating channel (name: %s, number: %s)", channel_name, channel)
    dtv_update_programs(number=channel, collection=collection, config=config, randomize=randomize)

    # update the poster
    if collection.poster_url:
        LOGGER.debug("Updating channel %s with poster at %s", channel_name, collection.poster_url)
        dtv_set_poster(config=config, number=channel, url=collection.poster_url)

    send_discord(config=config,
                 message="%s DizqueTV channel (name: %s, number %d)" % \
                 (operation, channel_name, channel))
    return Response(status_code=200)


def get_channel_name(section: str, name: str):
    """ get a channel name from a section and collection name """
    return "%s - %s" % (section, name)


def get_plex_connection(config: dict):
    """ get a plex connection """
    plex_url = config['plex']['url']
    plex_token = config['plex']['token']
    LOGGER.debug("Connecting to Plex at: %s", plex_url)
    return server.PlexServer(plex_url, plex_token)


def get_dtv_connection(config: dict):
    """ get a dizquetv connection """
    diz_url = config['dizquetv']['url']
    LOGGER.debug("Connecting to DizqueTV at: %s", diz_url)
    return API(url=diz_url, verbose=False)


def dtv_get_channel_number(config: dict, name: str):
    """ get a channel number from a channel name, '0' indicates channel does not exis """
    dtv_server = get_dtv_connection(config)
    for num in dtv_server.channel_numbers:
        this_channel = dtv_server.get_channel(channel_number=num)
        if this_channel.name == name:
            LOGGER.debug("Found channel, %d, for name %s", this_channel.number, this_channel.name)
            return this_channel.number

    return 0


def dtv_create_new_channel(config: dict, name: str, start_at: int):
    """ create a new channel by finding an unused channel number """
    dtv_server = get_dtv_connection(config)

    LOGGER.debug("Looking for an available channel number, starting at: %d", start_at)
    lowest = start_at
    if dtv_server.channel_numbers:
        # build a range of integers that is 1 longer than the number of
        # channels
        max_count = len(dtv_server.channel_numbers) + 1
        possible = range(start_at, start_at + max_count)
        # find the lowest number of the differences in the sets
        lowest = min(set(possible) - set(dtv_server.channel_numbers))

    LOGGER.debug("Lowest available channel number is %d", lowest)
    dtv_server.add_channel(programs=[],
                           number=lowest,
                           name=name,
                           handle_errors=True)

    return lowest


def dtv_delete_channel(config: dict, number: int):
    """ deletes a specified channel, by number """
    dtv_server = get_dtv_connection(config=config)
    return dtv_server.delete_channel(channel_number=number)


def dtv_set_poster(config: dict, number: int, url: str):
    """ sets the channel poster """
    dtv_server = get_dtv_connection(config=config)
    return dtv_server.update_channel(channel_number=number,
                                     icon=url)


def dtv_update_programs(config: dict, number: int, collection: Collection, randomize: bool = True):
    """ update the programming on a channel """
    LOGGER.info("Updating programs for channel: %d", number)
    dtv_server = get_dtv_connection(config=config)
    plex_server = get_plex_connection(config=config)

    # get the channel object
    chan = dtv_server.get_channel(channel_number=number)

    if chan == 0:
        LOGGER.error("Could not find DizqueTV channel for number: %d", number)
        return

    all_items = []

    # find all of the shows and movies in the collection
    LOGGER.debug("Gathering programs for channel")
    found_coll = plex_server.library.section(
        collection.library_name).search(
            title=collection.collection,
            libtype='collection')
    if found_coll and len(found_coll) == 1:
        all_items.extend(found_coll[0].items())

    # build list of programs (movies and episodes)
    total_minutes = 0
    if all_items:
        final_programs = []
        for item in all_items:
            if item.type == 'movie' or item.type == 'episode':
                final_programs.append(item)
            elif item.type == 'show':
                for episode in item.episodes():
                    if (hasattr(episode, "originallyAvailableAt") and \
                        episode.originallyAvailableAt) and (
                                hasattr(episode, "duration") and episode.duration):
                        final_programs.append(episode)

        # calculate the total duration of the programs
        for prog in final_programs:
            if (hasattr(prog, "duration") and prog.duration):
                total_minutes += (prog.duration/60000)

        # make sure the channel will play for at least a month (31 days)
        times_to_repeat = int((31*24*60)/total_minutes) + 1

        # remove existing content
        LOGGER.debug("Removing exiting programs from channel: %d", number)
        chan.delete_all_programs()
        # add new content
        LOGGER.debug("Adding new programs for channel: %d", number)
        chan.add_programs(programs=final_programs,
                          plex_server=plex_server)

        LOGGER.debug("Setting replicate count to %d", times_to_repeat)
        # sort things randomly
        if randomize:
            LOGGER.debug("Sortng programs randomly")
            chan.sort_programs_randomly()
            chan.replicate_and_shuffle(how_many_times=times_to_repeat)
        else:
            LOGGER.debug("Skipping the randmize of programs per config")
            chan.replicate(how_many_times=times_to_repeat)


def send_discord(config: dict, message: str):
    """ send a discord webhook """
    if 'discord' not in config['dizquetv'] or 'url' not in config['dizquetv']['discord']:
        LOGGER.debug("Discord webook not set, skipping notification")

    url = config['dizquetv']['discord']['url']
    username = 'pmm-dizquetv'
    if 'username' in config['dizquetv']['discord']:
        username = config['dizquetv']['discord']['username']
    avatar = 'https://github.com/tssgery/pmm-dizquetv/raw/main/avatar/discord-avatar.png'
    if 'avatar' in config['dizquetv']['discord']:
        avatar = config['dizquetv']['discord']['avatar']

    LOGGER.debug("Sending Discord webhook")

    discord = Discord(url=url)
    discord.post(
        content=message,
        username=username,
        avatar_url=avatar
    )
