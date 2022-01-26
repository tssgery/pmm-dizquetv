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


VERBOSE = False
# get the LOGGER, we wll use the ivucorn LOGGER to make format consistent
LOGGER = logging.getLogger("uvicorn.error")

with open("/config/config.yml", "r") as f:
    CONFIG = yaml.load(f, Loader=yaml.SafeLoader)
    LOGGER.info("Read configuration")
    LOGGER.info("PLEX URL set to: %s", CONFIG['plex']['url'])
    LOGGER.info("DizqueTV URL set to: %s", CONFIG['dizquetv']['url'])
    if not CONFIG['plex']['token']:
        LOGGER.error("No PLEX Token is set")
        sys.exit(1)
    if 'debug' in CONFIG['dizquetv'] and CONFIG['dizquetv']['debug']:
        LOGGER.info("DEBUG logging is enabled")
        LOGGER.setLevel(logging.DEBUG)
        VERBOSE = True
    else:
        LOGGER.info("Debug logging is disabled")
        LOGGER.setLevel(logging.INFO)

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

    # boolean as to if the channel needed to be created
    operation = "Updated"

    # make sure a collection name was provided
    if collection.collection is None:
        LOGGER.error("Null collection name was received")
        send_discord("ERROR: Null collection name was received")
        return Response(status_code=400)

    # calculate the dizquetv channel name
    channel_name = get_channel_name(
        section=collection.library_name,
        name=collection.collection)
    LOGGER.info("Channel name: %s", channel_name)

    # get the channel number, will return 0 if no channel exists
    channel = dtv_get_channel_number(channel_name)
    LOGGER.info("Channel number: %d", channel)

    # handle collection deletion
    if collection.deleted:
        LOGGER.debug("Deleting channel (name: %s, number: %s)", channel_name, channel)
        dtv_delete_channel(channel)
        send_discord("Deleted DizqueTV channel (name: %s, number %d)" % (channel_name, channel))
        return Response(status_code=200)

    # if the channel does not exist and we were not asked to delete it
    if channel == 0 and not collection.deleted:
        start_at = 1
        if 'libraries' in CONFIG and \
           collection.library_name in CONFIG['libraries'] and \
           'dizquetv_start' in CONFIG['libraries'][collection.library_name]:
            start_at = CONFIG['libraries'][collection.library_name]['dizquetv_start']
        LOGGER.debug("Creating channel (name: %s, number: %s)", channel_name, channel)
        channel = dtv_create_new_channel(name=channel_name, start_at=start_at)
        operation = "Created"

    # now remove the existing content and reset it
    LOGGER.debug("Updating channel (name: %s, number: %s)", channel_name, channel)
    dtv_update_programs(channel, collection)

    # update the poster
    if collection.poster_url:
        LOGGER.debug("Updating channel %s with poster at %s", channel_name, collection.poster_url)
        dtv_set_poster(channel, collection.poster_url)

    send_discord("%s DizqueTV channel (name: %s, number %d)" % (operation, channel_name, channel))
    return Response(status_code=200)


def get_channel_name(section: str, name: str):
    """ get a channel name from a section and collection name """
    return "%s - %s" % (section, name)


def get_plex_connection():
    """ get a plex connection """
    plex_url = CONFIG['plex']['url']
    plex_token = CONFIG['plex']['token']
    LOGGER.debug("Connecting to Plex at: %s", plex_url)
    return server.PlexServer(plex_url, plex_token)

def get_dtv_connection():
    """ get a dizquetv connection """
    diz_url = CONFIG['dizquetv']['url']
    LOGGER.debug("Connecting to DizqueTV at: %s", diz_url)
    return API(url=diz_url, verbose=VERBOSE)


def dtv_get_channel_number(name: str):
    """ get a channel number from a channel name, '0' indicates channel does not exis """
    dtv_server = get_dtv_connection()
    for num in dtv_server.channel_numbers:
        this_channel = dtv_server.get_channel(channel_number=num)
        if this_channel.name == name:
            LOGGER.debug("Found channel, %d, for name %s", this_channel.number, this_channel.name)
            return this_channel.number

    return 0


def dtv_create_new_channel(name: str, start_at: int):
    """ create a new channel by finding an unused channel number """
    dtv_server = get_dtv_connection()

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


def dtv_delete_channel(number: int):
    """ deletes a specified channel, by number """
    dtv_server = get_dtv_connection()
    return dtv_server.delete_channel(channel_number=number)


def dtv_set_poster(number: int, url: str):
    """ sets the channel poster """
    dtv_server = get_dtv_connection()
    return dtv_server.update_channel(channel_number=number,
                                     icon=url)


def dtv_update_programs(number: int, collection: Collection):
    """ update the programming on a channel """
    LOGGER.info("Updating programs for channel: %d", number)
    dtv_server = get_dtv_connection()
    plex_server = get_plex_connection()

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

        # remove existing content
        LOGGER.debug("Removing exiting programs from channel: %d", number)
        chan.delete_all_programs()
        # add new content
        LOGGER.debug("Adding new programs for channel: %d", number)
        chan.add_programs(programs=final_programs,
                          plex_server=plex_server)
        # sort things randomly
        LOGGER.debug("Sortng programs randomly")
        chan.sort_programs_randomly()

def send_discord(message: str):
    """ send a discord webhook """
    if 'discord' not in CONFIG['dizquetv'] or 'url' not in CONFIG['dizquetv']['discord']:
        LOGGER.debug("Discord webook not set, skipping notification")

    url = CONFIG['dizquetv']['discord']['url']
    username = 'pmm-dizquetv'
    if 'username' in CONFIG['dizquetv']['discord']:
        username = CONFIG['dizquetv']['discord']['username']
    avatar = 'https://github.com/tssgery/pmm-dizquetv/raw/main/avatar/discord-avatar.png'
    if 'avatar' in CONFIG['dizquetv']['discord']:
        avatar = CONFIG['dizquetv']['discord']['avatar']

    LOGGER.debug("Sending Discord webhook")
    LOGGER.debug("Discord: %s", url)
    LOGGER.debug("Username: %s", username)
    LOGGER.debug("Avatar: %s", avatar)
    LOGGER.debug("Message: %s", message)

    discord = Discord(url=url)
    discord.post(
        content=message,
        username=username,
        avatar_url=avatar
    )
