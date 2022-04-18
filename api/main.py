"""
Provides webhook call for Plex-Meta-Manager, to create DizqueTV channels
"""

# pylint: disable=import-error
# pylint: disable=too-many-branches
# pylint: disable=too-many-locals
# pylint: disable=too-many-statements

import sys
from pprint import pformat
from typing import Optional

from discordwebhook import Discord
from dizqueTV import API
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from plexapi import server
from pydantic import BaseModel

import pmmdtv_config
import pmmdtv_logger

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


class StartRun(BaseModel):  # pylint: disable=too-few-public-methods
    """
    Class to encapsulate the payload from Plex-Meta-Manager, run starting
    """
    start_time: Optional[str]


class EndRun(BaseModel):  # pylint: disable=too-few-public-methods
    """
    Class to encapsulate the payload from Plex-Meta-Manager, run ending
    """
    start_time: Optional[str]
    end_time: Optional[str]
    run_time: Optional[str]
    collections_created: Optional[int]
    collections_modified: Optional[int]
    collections_deleted: Optional[int]
    items_added: Optional[int]
    items_removed: Optional[int]
    added_to_radarr: Optional[int]
    added_to_sonarr: Optional[int]


class Collection(BaseModel):  # pylint: disable=too-few-public-methods
    """
    Class to encapsulate the payload from Plex-Meta-Manager, changes
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


@APP.on_event("startup")
async def startup_event():
    """
    APP initialization code
    """
    config = pmmdtv_config.get_config(validate=True)
    logger = pmmdtv_logger.get_logger()
    logger.info("Read configuration")
    logger.info("PLEX URL set to: %s", config['plex']['url'])
    logger.info("DizqueTV URL set to: %s", config['dizquetv']['url'])
    if not config['plex']['token']:
        logger.error("No PLEX Token is set")
        sys.exit(1)


@APP.post("/start", status_code=200)
def hook_start(start_time: StartRun):
    """ Webhook for when a PMM run starts """
    logger = pmmdtv_logger.get_logger()
    logger.info("PMM Run started at: %s", start_time.start_time)
    # Validate the configuration
    _ = pmmdtv_config.get_config(validate=True)
    return Response(status_code=200)


@APP.post("/end", status_code=200)
def hook_end(end_time: EndRun):
    """ Webhook for when a PMM run ends """
    logger = pmmdtv_logger.get_logger()
    logger.info("PMM Run ended at: %s", end_time.end_time)
    return Response(status_code=200)


@APP.post("/collection", status_code=200)
def hook_update(collection: Collection):
    """The actual webhook, /collection, which gets all collection updates"""
    logger = pmmdtv_logger.get_logger()
    logger.debug(pformat(collection))

    config = pmmdtv_config.get_config()

    # boolean as to if the channel needed to be created
    operation = "Updated"

    # make sure a collection name was provided
    if collection.collection is None:
        logger.error("Null collection name was received")
        send_discord(config=config, message="ERROR: Null collection name was received")
        return Response(status_code=400)

    col_name = collection.collection
    col_section = collection.library_name

    # check if the collection or library is marked to be ignored
    if pmmdtv_config.get_ignore_channel(col_section=col_section, col_name=col_name):
        logger.info("Ignoring collection: %s", col_name)
        return Response(status_code=200)

    # calculate the dizquetv channel name
    channel_name = pmmdtv_config.get_channel_name(
        col_section=col_section,
        col_name=col_name)
    logger.info("Channel name: %s", channel_name)

    # get the channel number, will return 0 if no channel exists
    channel = dtv_get_channel_number(config=config, name=channel_name)
    logger.info("Channel number: %d", channel)

    # handle collection deletion
    if collection.deleted:
        logger.debug("Deleting channel (name: %s, number: %s)", channel_name, channel)
        dtv_delete_channel(config=config, number=channel)
        send_discord(config=config,
                     message=f"Deleted DizqueTV channel (name: {channel_name}, number {channel})")
        return Response(status_code=200)

    # if the channel does not exist and we were not asked to delete it
    if channel == 0 and not collection.deleted:
        logger.debug("Creating channel (name: %s, number: %s)", channel_name, channel)
        channel = dtv_create_new_channel(config=config, name=channel_name)
        operation = "Created"

    # determine if the channel contents should be randomized
    randomize = pmmdtv_config.get_random(col_section=col_section,
                                         col_name=col_name)

    # get the channel group and set it
    channel_group = pmmdtv_config.get_channel_group(col_section=col_section,
                                                    col_name=col_name)
    if channel_group:
        logger.debug("Setting Channel Group (number: %s) to: %s", channel, channel_group)
        dtv_set_channel_group(config=config,
                              number=channel,
                              channel_group=channel_group)

    # now remove the existing content and reset it
    logger.debug("Updating channel (name: %s, number: %s)", channel_name, channel)
    dtv_update_programs(number=channel, collection=collection, config=config, randomize=randomize)

    # update the poster
    if collection.poster_url:
        logger.debug("Updating channel %s with poster at %s", channel_name, collection.poster_url)
        dtv_set_poster(config=config, number=channel, url=collection.poster_url)

    send_discord(config=config,
                 message=f"{operation} DizqueTV channel (name: {channel_name}, number: {channel})")
    return Response(status_code=200)


def get_plex_connection(config: dict):
    """ get a plex connection """
    plex_url = config['plex']['url']
    plex_token = config['plex']['token']
    logger = pmmdtv_logger.get_logger()
    logger.debug("Connecting to Plex at: %s", plex_url)
    return server.PlexServer(plex_url, plex_token)


def get_dtv_connection(config: dict):
    """ get a dizquetv connection """
    diz_url = config['dizquetv']['url']
    logger = pmmdtv_logger.get_logger()
    logger.debug("Connecting to DizqueTV at: %s", diz_url)
    return API(url=diz_url, verbose=False)


def dtv_get_channel_number(config: dict, name: str):
    """ get a channel number from a channel name, '0' indicates channel does not exist """
    dtv_server = get_dtv_connection(config)
    logger = pmmdtv_logger.get_logger()
    for num in dtv_server.channel_numbers:
        this_channel = dtv_server.get_channel(channel_number=num)
        if this_channel.name == name:
            logger.debug("Found channel, %d, for name %s", this_channel.number, this_channel.name)
            return this_channel.number

    return 0


def dtv_create_new_channel(config: dict, name: str):
    """ create a new channel by finding an unused channel number """
    dtv_server = get_dtv_connection(config)
    logger = pmmdtv_logger.get_logger()
    logger.debug("Looking for the lowest available channel number")
    lowest_available = dtv_server.lowest_available_channel_number
    logger.debug("Lowest available channel number is %d", lowest_available)
    dtv_server.add_channel(programs=[],
                           number=lowest_available,
                           name=name,
                           handle_errors=True)

    return lowest_available


def dtv_delete_channel(config: dict, number: int):
    """ deletes a specified channel, by number """
    dtv_server = get_dtv_connection(config=config)
    return dtv_server.delete_channel(channel_number=number)


def dtv_set_poster(config: dict, number: int, url: str):
    """ sets the channel poster """
    dtv_server = get_dtv_connection(config=config)
    return dtv_server.update_channel(channel_number=number,
                                     icon=url)


def dtv_set_channel_group(config: dict, number: int, channel_group: str):
    """ sets the channel group """
    dtv_server = get_dtv_connection(config=config)
    return dtv_server.update_channel(channel_number=number,
                                     groupTitle=channel_group)


def dtv_update_programs(config: dict, number: int, collection: Collection, randomize: bool = True):
    """ update the programming on a channel """
    logger = pmmdtv_logger.get_logger()
    logger.info("Updating programs for channel: %d", number)
    dtv_server = get_dtv_connection(config=config)
    plex_server = get_plex_connection(config=config)

    # get the channel object
    chan = dtv_server.get_channel(channel_number=number)

    if chan == 0:
        logger.error("Could not find DizqueTV channel for number: %d", number)
        return

    all_items = []

    # find all shows and movies in the collection
    logger.debug("Gathering programs for channel")
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
            if item.type in ('movie', 'episode'):
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
                total_minutes += (prog.duration / 60000)

        # make sure the channel will play for at least a number of days
        min_days = pmmdtv_config.get_minimum_days(col_section=collection.library_name,
                                                  col_name=collection.collection)
        times_to_repeat = int((min_days * 24 * 60) / total_minutes) + 1

        # remove existing content
        logger.debug("Removing exiting programs from channel: %d", number)
        chan.delete_all_programs()
        # add new content
        logger.debug("Adding new programs for channel: %d", number)
        chan.add_programs(programs=final_programs,
                          plex_server=plex_server)

        # add fillers if requested
        chan.delete_all_filler_lists()
        fillers = pmmdtv_config.get_filler_lists(col_section=collection.library_name,
                                                 col_name=collection.collection)
        for a_filler in fillers:
            logger.debug("Adding Filler List: %s", a_filler)
            filler_list = dtv_server.get_filler_list_by_name(a_filler)
            if filler_list:
                chan.add_filler_list(filler_list=filler_list)
            else:
                logger.debug("Unable to find Filler List: %s", a_filler)

        logger.debug("Setting replicate count to %d", times_to_repeat)
        # sort things randomly
        if randomize:
            logger.debug("Sortng programs randomly")
            chan.sort_programs_randomly()
            chan.replicate_and_shuffle(how_many_times=times_to_repeat)
        else:
            logger.debug("Skipping the randmize of programs per config")
            chan.replicate(how_many_times=times_to_repeat)

        # set padding if requested
        pad = pmmdtv_config.get_pad_time(col_section=collection.library_name,
                                         col_name=collection.collection)
        if pad and pad != 0:
            logger.debug("Setting time padding to %d minutes", pad)
            chan.pad_times(start_every_x_minutes=pad)
        else:
            logger.debug("Padding is disabled")


def send_discord(config: dict, message: str):
    """ send a discord webhook """
    logger = pmmdtv_logger.get_logger()
    if 'discord' not in config['dizquetv'] or 'url' not in config['dizquetv']['discord']:
        logger.debug("Discord webhook not set, skipping notification")

    url = config['dizquetv']['discord']['url']
    username = 'pmm-dizquetv'
    if 'username' in config['dizquetv']['discord']:
        username = config['dizquetv']['discord']['username']
    avatar = 'https://github.com/tssgery/pmm-dizquetv/raw/main/avatar/discord-avatar.png'
    if 'avatar' in config['dizquetv']['discord']:
        avatar = config['dizquetv']['discord']['avatar']

    logger.debug("Sending Discord webhook")

    discord = Discord(url=url)
    discord.post(
        content=message,
        username=username,
        avatar_url=avatar
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(APP, host="0.0.0.0", port="8000", log_config=pmmdtv_logger.get_config())
