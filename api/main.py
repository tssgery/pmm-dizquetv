"""
Provides webhook call for Plex-Meta-Manager, to create DizqueTV channels
"""

# pylint: disable=import-error
# pylint: disable=too-many-branches
# pylint: disable=too-many-locals
# pylint: disable=too-many-statements

import sys
from concurrent.futures.process import ProcessPoolExecutor
from pprint import pformat
from typing import Optional

from dizqueTV import API
from fastapi import FastAPI, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from plexapi import server
from pydantic import BaseModel

import pmmdtv_config
import pmmdtv_discord
import pmmdtv_logger

# create the API
APP = FastAPI()

# globals for reporting purposes
# igmored collections
ignored_collections = []

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

class DeleteCollection(BaseModel):  # pylint: disable=too-few-public-methods
    """
    Class to encapsulate the payload from Plex-Meta-Manager, delete webhook
    """
    server_name: Optional[str]
    library_name: Optional[str]
    message: Optional[str]

@APP.on_event("startup")
async def startup_event():
    """
    APP initialization code
    """
    APP.state.executor = ProcessPoolExecutor()

    config = pmmdtv_config.get_config(validate=True)
    logger = pmmdtv_logger.get_logger()
    logger.info("Read configuration")
    logger.info("PLEX URL set to: %s", config['plex']['url'])
    logger.info("DizqueTV URL set to: %s", config['dizquetv']['url'])
    if not config['plex']['token']:
        logger.error("No PLEX Token is set")
        sys.exit(1)

@APP.on_event("shutdown")
async def on_shutdown():
    """
    APP termination code
    """
    APP.state.executor.shutdown()


@APP.post("/start", status_code=200)
def hook_start(start_time: StartRun):
    """ Webhook for when a PMM run starts """
    logger = pmmdtv_logger.get_logger()
    logger.info("PMM Run started at: %s", start_time.start_time)
    # reset the list of ignored collections
    ignored_collections = []
    # Validate the configuration
    _ = pmmdtv_config.get_config(validate=True)
    return Response(status_code=200)


@APP.post("/end", status_code=200)
def hook_end(end_time: EndRun):
    """ Webhook for when a PMM run ends """
    logger = pmmdtv_logger.get_logger()
    logger.info("PMM Run ended at: %s", end_time.end_time)
    message = "Plex-Meta-Manager run complete, "
    message += "collections/channels will continue in the background."

    if ignored_collections:
        message += "\nThe following collections were updated but "
        message += "ignored due to pmm-dizquetv configuration:\n"
        for this_coll in ignored_collections:
            message += "- " + this_coll + "\n"

    logger.info(message)
    return Response(status_code=200)


@APP.post("/collection", status_code=202)
def hook_update(collection: Collection, background_tasks: BackgroundTasks):
    """The actual webhook, /collection, which gets all collection updates"""
    logger = pmmdtv_logger.get_logger()
    logger.debug("Collection Requested: %s", pformat(collection))

    # get the collection config and see if we should ignore this one
    channel_config = pmmdtv_config.get_collection_config(col_section=collection.library_name,
                                                         col_name=collection.collection)
    full_name = collection.library_name + " - " + collection.collection

    # check if the collection or library is marked to be ignored
    if channel_config['ignore']:
        ignored_collections.append(full_name)
        logger.info("Ignoring collection: %s, because the 'ignore' flag was set", full_name)
    else:
        # Process the collection in the background
        background_tasks.add_task(process_collection, collection)

    # send back an ACCEPTED response, regardless of if it is ignored
    return Response(status_code=202)

@APP.post("/delete", status_code=200)
def hook_delete(collection: DeleteCollection):
    """ Webhook for when a PMM collection is deleted """
    logger = pmmdtv_logger.get_logger()
    logger.info("Collection deleted: %s", pformat(collection))

    config = pmmdtv_config.get_config()

    # get the collection config and see if we should ignore this one
    channel_config = pmmdtv_config.get_collection_config(col_section=collection.library_name,
                                                         col_name=collection.message)
    channel_name = collection.library_name + " - " + collection.message

    # get the channel number, will return 0 if no channel exists
    channel = dtv_get_channel_number(config=config, name=channel_name)
    if channel == 0:
        # channel not found
        logger.info("Ignoring deletion of channel: %s, because it was not found in dizquetv",
                    channel_name)
        return Response(status_code=200)

    # check if the collection or library is marked to be ignored
    if channel_config['ignore']:

        logger.info("Ignoring deletion of channel: %s, because the 'ignore' flag was set",
                    channel_name)
        return Response(status_code=200)

    # handle collection deletion
    logger.debug("Deleting channel (name: %s, number: %s)", channel_name, channel)
    dtv_delete_channel(config=config, number=channel)
    pmmdtv_discord.send_discord(config=config,
                                message="Channel Deleted",
                                channel_name=channel_name,
                                channel_number=channel)
    return Response(status_code=200)

def process_collection(collection: Collection):
    """ background tasks to process the collection """
    logger = pmmdtv_logger.get_logger()
    logger.debug("Processing %s", collection.collection)

    config = pmmdtv_config.get_config()

    # boolean as to if the channel needed to be created
    operation = "Updated"

    # make sure a collection name was provided
    if collection.collection is None:
        logger.error("Null collection name was received")
        return

    col_name = collection.collection
    col_section = collection.library_name

    channel_config = pmmdtv_config.get_collection_config(col_section=col_section,
                                                         col_name=col_name)
    logger.debug("Collection Config: %s", pformat(channel_config))

    channel_name = channel_config['channel_name']
    logger.info("Channel name: %s", channel_name)

    # get the channel number, will return 0 if no channel exists
    channel = dtv_get_channel_number(config=config, name=channel_name)
    logger.info("Channel number: %d", channel)

    # if the channel does not exist
    if channel == 0:
        logger.debug("Creating channel (name: %s, number: %s)", channel_name, channel)
        channel = dtv_create_new_channel(config=config, name=channel_name)
        operation = "Created"

    # get the channel group and set it
    if channel_config['channel_group']:
        logger.debug("Setting Channel Group (number: %s) to: %s",
                     channel,
                     channel_config['channel_group'])
        dtv_set_channel_group(config=config,
                              number=channel,
                              channel_group=channel_config['channel_group'])

    # now remove the existing content and reset it
    logger.debug("Updating channel (name: %s, number: %s)", channel_name, channel)
    progs, minutes = dtv_update_programs(number=channel,
                                         collection=collection,
                                         config=config,
                                         channel_config=channel_config)

    # update the poster
    if collection.poster_url:
        logger.debug("Updating channel %s with poster at %s", channel_name, collection.poster_url)
        dtv_set_poster(config=config, number=channel, url=collection.poster_url)

    pmmdtv_discord.send_discord(config=config,
                                message=f"Channel {operation}",
                                channel_name=channel_name,
                                channel_number=channel,
                                channel_programs=progs,
                                channel_playtime=minutes)

    return

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
    # assume the lowest channel number is #1
    lowest_available = 1
    # if channels exist, get the lowest_available
    if len(dtv_server.channel_numbers) > 0:
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


def dtv_update_programs(config: dict, channel_config: dict, number: int, collection: Collection):
    """ update the programming on a channel """
    logger = pmmdtv_logger.get_logger()
    logger.info("Channel %d: Updating programs", number)
    dtv_server = get_dtv_connection(config=config)
    plex_server = get_plex_connection(config=config)

    # get the channel object
    chan = dtv_server.get_channel(channel_number=number)

    if chan == 0:
        logger.error("Could not find DizqueTV channel for number: %d", number)
        return 0,0

    all_items = []

    # find all shows and movies in the collection
    logger.debug("Channel %d: Gathering programs", number)
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

        channel_programs = len(final_programs)
        channel_playtime = total_minutes

        # make sure the channel will play for at least a number of days
        min_days = channel_config['minimum_days']
        times_to_repeat = int((min_days * 24 * 60) / total_minutes) + 1

        # remove existing content
        logger.debug("Channel %d: Removing exiting programs", number)
        chan.delete_all_programs()
        # add new content
        logger.debug("Channel %d: Adding new programs", number)
        # add items in chunks of 100 to allow the event loop some time
        for i in range(0, len(final_programs), 100):
            # taking the slice pulls up to, but not including the end number
            logger.debug("Channel %d: Adding programs, %d-%d (total: %d)",
                         number,
                         i+1,
                         i+100,
                         len(final_programs))
            chan.add_programs(programs=final_programs[i:i+100],
                              plex_server=plex_server)

        # add fillers if requested
        chan.delete_all_filler_lists()
        fillers = channel_config['fillers']

        for a_filler in fillers:
            logger.debug("Channel %d: Adding Filler List: %s", number, a_filler)
            filler_list = dtv_server.get_filler_list_by_name(a_filler)
            if filler_list:
                chan.add_filler_list(filler_list=filler_list)
            else:
                logger.debug("Channel %d: Unable to find Filler List: %s", number, a_filler)

        logger.debug("Channel %d: Setting replicate count to %d", number, times_to_repeat)

        # sort things randomly
        if channel_config['random']:
            logger.debug("Channel %d: Sorting programs randomly", number)
            chan.cyclical_shuffle()
        else:
            logger.debug("Channel %d: Skipping the randomize of programs per config", number)

        chan.replicate(how_many_times=times_to_repeat)

        # set padding if requested
        pad = channel_config['pad']
        if pad and pad != 0:
            logger.debug("Channel %d: Setting time padding to %d minutes", number, pad)
            chan.pad_times(start_every_x_minutes=pad)
        else:
            logger.debug("Channel %d: Padding is disabled", number)

        return channel_programs, channel_playtime

    return 0,0

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(APP, host="0.0.0.0", port="8000", log_config=pmmdtv_logger.get_config())
