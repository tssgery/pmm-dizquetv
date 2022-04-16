# pmm-dizquetv

Small service that can synchronize Plex Collections, managed by Plex-Meta-Manger,
with DizqueTV channels.

It achieves this by exposing a webhook that can be configured within Plex-Meta-Manager,
to eb called whenever a Collection is created, modified, or deleted. When receiving the
webhook call, pmm-dizquetv will utilize the DizqueTV API to keep channels in sync.

<a href="https://www.buymeacoffee.com/tssgery" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>

## Contributions
Contributions to this project are always welcome. Pull requests to the `main` branch are checked with the following actions:
* Pylint - Checks are run against python 3.8, 3.9, and 3.10
* Docker build - Docker images are built to verify requirements and packaging

Any failures in the actions will cause the PR to be un-mergable until resolved.

## Getting Started

### configuration
pmm-dizquetv will read its configuration from a file named `/config/config.yml`, and example file can be found
at the root of this repo, and looks like:

```
---
plex:
  url: "INSERT_PLEX_URL_HERE:32400"
  token: "INSERT_PLEX_TOKEN_HERE"
dizquetv:
  url: "INSERT_DIZQUETV_URL_HERE:8000"
  debug: True
  discord:
    url: "INSERT_DISCORD_WEBHOOK_URL_HERE"
    username: "pmm-dizquetv"
    avatar: "https://github.com/tssgery/pmm-dizquetv/raw/main/avatar/discord-avatar.png"
defaults:
  Movies:
    pad: 10
    fillers:
      - Trailers
    channel_group: Movies
  TV Shows:
    pad: 5
    minimum_days: 7
    fillers:
      - Commercials
    channel_group: TV
libraries:
  Movies:
    Pixar:
      pad: 5
      fillers:
        - Kid Safe Trailers
  TV Shows:
    Friends:
      minimum_days: 31
      random: false
      pad: 2
      channel_name: NBC - Friends
      channel_group: Must See TV
    Lost: 
      ignore: True
      random: false
```

#### plex
The `plex` section of the configuration points to the location and the authorization token for your plex instance

##### dizquetv
The `dizquetv` section points to your DizqueTV instances and provides a location for more general configuration values,
such as

| value   | setting                                                             |
|---------|---------------------------------------------------------------------|
| debug   | enable pmm-dizquetv logging debug verbosity, default is `false`     |
| discord | pmm-dizquetv can send notifications to discord, if settings applied |
|         | `url`: Discord webhook url                                          |
|         | `username`: Username for discord, `pmm-dizquetv` is default         |
|         | `avatar`: url of the avatar to display in Discord                   |

#### defaults
The `defaults` section allows for overriding the default values for each `library`

| value     | setting                                                                                   |
|-----------|-------------------------------------------------------------------------------------------|
| `library` | Allows for customizing the defaults the specified library.                                |
|           | `random`: randomize the programs within the channel. Default is `true`                    |   
|           | `minimum_days`: repeat programming until a specific number of days is met. Default is '0' |
|           | `fillers`: a list of filler Lists already defined within DizqueTV                         |
|           | `channel_group`: Default value for the Channel within DizqueTV                            |
|           | `ignore`: Ignore any changes made to any collection in this library                       |


#### libraries
The `libraries` section is not required but allows the override of default behaviour. 

The children of the `libraries` section are the section names within Plex, and within those sections,
the following can be defined:

| value          | setting                                                                                                   |
|----------------|-----------------------------------------------------------------------------------------------------------|
| dizquetv_start | Starting channel number within DizqueTV. By default the first unused number will be used.                 |
|                | If set, pmm-dizquetv will use the first unused number, greater than or equal to this.                     |
| `collection`   | Allows for customizing the channel configuration for the specified collection.                            |
|                | `random`: randomize the programs within the channel. Default is `true`                                    |   
|                | `minimum_days`: repeat programming until a specific number of days is met. Default is '0'                 |
|                | `fillers`: a list of filler Lists already defined within DizqueTV                                         |
|                | `channel_name`: Allows a manually specified channel name. Default is `<plex_library> - <plex_collection>` |
|                | `channel_group`: Value for the Channel within DizqueTV                                                    |
|                | `ignore`: Ignore any changes made to this collection                                                      |


### docker-compose
pmm-dizquetv is built as a container image and can be run via `docker-compose` via a configuration file such as 

```
version: "3"
services:
  pmm-dizquetv:
    container_name: pmm-dizquetv
    image: tssgery/pmm-dizquetv:latest
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
    volumes:
      - /path/to/pmm-dizquetv/config:/config:ro
    restart: unless-stopped
    ports:
      - "8000:8000"
```

### Enabling within Plex-Meta-Manager
Enabling pmm-dizquetv is simple, just add it as a target for the `changes` webhook within PMM.

For example, the following snippet from the PMM config would send notify both notifiarr and pmm-dizquetv of changes

```
webhooks:
  error: notifiarr
  run_start: notifiarr
  run_end: notifiarr
  changes:
    - notifiarr
    - http://pmm-dizquetv:8000/collection
```lint
