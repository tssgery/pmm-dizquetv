"""
Provides webhook call for Plex-Meta-Manager, to create DizqueTV channels
"""

# pylint: disable=import-error

import datetime

from discord_webhook import DiscordWebhook, DiscordEmbed
import human_readable

import pmmdtv_logger

# pylint: disable=R0913
def send_discord(config: dict,
                 message: str,
                 channel_name: str,
                 channel_number: int,
                 channel_programs: int = 0,
                 channel_playtime: int = 0):
    """ send a notification that the channel is processed """
    logger = pmmdtv_logger.get_logger()
    if 'discord' not in config['dizquetv'] or 'url' not in config['dizquetv']['discord']:
        logger.debug("Discord webhook not set, skipping notification")
    username = 'pmm-dizquetv'
    if 'username' in config['dizquetv']['discord']:
        username = config['dizquetv']['discord']['username']

    webhook = DiscordWebhook(url=config['dizquetv']['discord']['url'])

    embed = DiscordEmbed(
        title=username + ": " + message, color='03b2f8'
    )

    embed.set_footer(text="PMM-Diszquetv: A PMM -> DizqueTV synchronizer")
    embed.set_timestamp()
    # Set `inline=False` for the embed field to occupy the whole line
    embed.add_embed_field(name="Channel Number", value=channel_number)
    embed.add_embed_field(name="Channel Name", value=channel_name)
    if channel_programs > 0:
        embed.add_embed_field(name="Total Programs", value=channel_programs, inline=False)
    if channel_playtime > 0:
        #time_formatted = str(datetime.timedelta(minutes = channel_playtime))
        time_formatted = human_readable.precise_delta(
            datetime.timedelta(minutes = channel_playtime))
        embed.add_embed_field(name="Programming Duration", value=time_formatted, inline=False)

    webhook.add_embed(embed)
    _ = webhook.execute()
