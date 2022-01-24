
import logging
import sys
import yaml

from dizqueTV import API
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from plexapi import server
from pydantic import BaseModel
from typing import Optional


logger = logging.getLogger("uvicorn.error")

with open("/config/config.yml", "r") as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)
    logger.info("Read configuration")
    logger.info("PLEX URL set to: %s" % config['plex']['url'])
    logger.info("DizqueTV URL set to: %s" % config['dizquetv']['url'])
    if not config['plex']['token']:
        logger.error("No PLEX Token is set")
        sys.exit(1)

app = FastAPI()

origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


class Collection(BaseModel):
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
    changed: Optional[bool]


@app.post("/collection", status_code=200)
async def create_Deployment(collection: Collection):

    # make sure a collection name was provided
    if collection.collection is None:
        logger.error("Null collection name was received")
        return Response(status_code=400)

    # figure out if the collection is being created, deleted, or changed
    if (collection.created is None or collection.created == False) and \
       (collection.deleted == None or collection.deleted == False):
        collection.changed = True

    # calculate the dizquetv channel name
    channel_name = get_channel_name(
        section=collection.library_name,
        name=collection.collection)
    logger.info("Channel name: %s" % channel_name)

    # get the channel number, will return 0 if no channel exists
    channel = dtv_get_channel_number(channel_name)
    logger.info("Channel number: %d" % channel)

    # handle collection deletion
    if collection.deleted:
        logger.debug("Deleting channel (name: %s, number: %s)" % (channel_name, channel))
        dtv_delete_channel(channel)
        return Response(status_code=200)

    # if the channel does not exist and we were not asked to delete it
    if channel == 0 and not collection.deleted:
        start_at = 1
        if config['libraries'] and \
           config['libraries'][collection.library_name] and \
           config['libraries'][collection.library_name]['dizquetv_start']:
            start_at = config['libraries'][collection.library_name]['dizquetv_start']
        logger.debug("Creating channel (name: %s, number: %s)" % (channel_name, channel))
        channel = dtv_create_new_channel(name=channel_name, start_at=start_at)

    # now remove the existing content and reset it
    logger.debug("Updating channel (name: %s, number: %s)" % (channel_name, channel))
    dtv_update_programs(channel, collection)

    # update the poster
    if collection.poster_url:
        logger.debug("Updating channel %s with poster at %s" % (channel_name, collection.poster_url))
        dtv_set_poster(channel, collection.poster_url)

    return Response(status_code=200)


# get a channel name from a section and collection name
def get_channel_name(section: str, name: str):
    return("%s - %s" % (section, name))

#
# Plex connection
def get_plex_connection():
    return server.PlexServer(config['plex']['url'], config['plex']['token'])

#
# DizqueTV interaction code
def get_dtv_connection():
    return API(url=config['dizquetv']['url'], verbose=False)

# get a channel number from a channel name
# returning a channel of '0' indicates channel does not exist
def dtv_get_channel_number(name: str):
    dtv_server = get_dtv_connection()
    for num in dtv_server.channel_numbers:
        ch = dtv_server.get_channel(channel_number=num)
        if ch.name == name:
            return ch.number

    return 0


# create a new channel by finding an unused channel number
def dtv_create_new_channel(name: str, start_at: int):
    dtv_server = get_dtv_connection()

    lowest = start_at
    if len(dtv_server.channel_numbers) > 0:
        # build a range of integers that is 1 longer than the number of
        # channels
        max_count = len(dtv_server.channel_numbers) + 1
        possible = range(start_at, start_at + max_count)
        # find the lowest number of the differences in the sets
        lowest = min(set(possible) - set(dtv_server.channel_numbers))

    dtv_server.add_channel(programs=[],
                           number=lowest,
                           name=name,
                           handle_errors=True)

    return lowest


# deletes a specified channel, by number
def dtv_delete_channel(number: int):
    dtv_server = get_dtv_connection()
    return dtv_server.delete_channel(channel_number=number)


# sets the channel poster
def dtv_set_poster(number: int, url: str):
    dtv_server = get_dtv_connection()
    return dtv_server.update_channel(channel_number=number,
                                     icon=url)


# update the programming on a channel
def dtv_update_programs(number: int, collection: Collection):
    dtv_server = get_dtv_connection()
    plex_server = get_plex_connection()

    # get the channel object
    chan = dtv_server.get_channel(channel_number=number)

    if chan == 0:
        return

    all_items = []

    # find all of the shows and movies in the collection
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
            if item.type == 'movie':
                final_programs.append(item)
            elif item.type == 'show':
                for episode in item.episodes():
                    if (hasattr(episode, "originallyAvailableAt") and episode.originallyAvailableAt) and (
                            hasattr(episode, "duration") and episode.duration):
                        final_programs.append(episode)

        # remove existing content
        chan.delete_all_programs()
        # add new content
        chan.add_programs(programs=final_programs,
                          plex_server=plex_server)
