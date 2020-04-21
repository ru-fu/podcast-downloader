import os
import time
import itertools
import urllib
import json

from datetime import datetime
from functools import partial
from dataclasses import dataclass

import feedparser


# Logger

def log(message, *paramaters):
    msg = message.replace('{}', '\033[97m{}\033[0m').format(*paramaters) if paramaters else message
    print(f'[\033[2m{datetime.now():%Y-%m-%d %H:%M:%S}\033[0m] {msg}')


# Configuration

def load_configuration_file(file_path):
    with open(file_path) as json_file:
        return json.load(json_file)


# Downloaded directory

def get_last_downloaded(podcast_directory: str):

    def get_downloaded_files(podcast_directory: str) -> [str]:
        return (file
                for file in sorted(os.listdir(podcast_directory), reverse=True)
                if file.endswith('.mp3') and os.path.isfile(os.path.join(podcast_directory, file)))

    return next(get_downloaded_files(podcast_directory))


# RSS

@dataclass
class RSSEntity():
    published_date: time.struct_time
    link: str


@dataclass
class RSSEntitySimpleName(RSSEntity):

    def to_file_name(self) -> str:
        return self.link.rpartition('/')[-1].lower()

@dataclass
class RSSEntityWithDate(RSSEntity):

    def to_file_name(self) -> str:
        podcast_name = RSSEntitySimpleName.to_file_name(self)
        return f'[{time.strftime("%Y%m%d", self.published_date)}] {podcast_name}'


def get_raw_rss_entries_from_web(rss_link: str) -> list:
    yield from feedparser.parse(rss_link).entries


def get_rss_entities(build_rss_entity, get_raw_rss_entries):

    def strip_data(raw_rss_entry: {}) -> ():

        def only_audio(link):
            return link.type == 'audio/mpeg'

        return (raw_rss_entry.published_parsed, list(filter(only_audio, raw_rss_entry.links)))

    def has_entry_podcast_link(strip_rss_entry: {}) -> bool:
        return len(strip_rss_entry[1]) > 0

    return map(
        build_rss_entity,
        filter(
            has_entry_podcast_link,
            map(
                strip_data,
                get_raw_rss_entries())))


# Main script

def only_new_entites(get_raw_rss_entries, get_last_downloaded_file) -> [RSSEntity]:
    last_downloaded_file = get_last_downloaded_file()

    return itertools.takewhile(
        lambda rss_entity: rss_entity.to_file_name() != last_downloaded_file,
        get_raw_rss_entries())


def build_to_download_list(podcast_directory: str, rss_link: str, require_date: bool):


    def build_rss_entity(constructor, strip_rss_entry):
        return constructor(strip_rss_entry[0], strip_rss_entry[1][0].href)


    get_last_downloaded_file = partial(get_last_downloaded, podcast_directory)
    get_all_rss_entities = partial(
        get_rss_entities,
        partial(
            build_rss_entity,
            RSSEntityWithDate if require_date else RSSEntitySimpleName
        ),
        partial(get_raw_rss_entries_from_web, rss_link))

    return only_new_entites(get_all_rss_entities, get_last_downloaded_file)


def download_rss_entity_to_path(path, rss_entity: RSSEntity):
    return urllib.request.urlretrieve(
        rss_entity.link,
        os.path.join(path, rss_entity.to_file_name()))


if __name__ == '__main__':
    import sys

    CONFIG_FILE = 'config.json'
    log('Loading configuration (from file: "{}")', CONFIG_FILE)
    CONFIG = load_configuration_file(CONFIG_FILE)

    DOWNLOADS_LIMITS = int(sys.argv[2]) \
        if len(sys.argv) > 2 and sys.argv[1] == '--downloads_limit' and sys.argv[2].isalnum() \
        else sys.maxsize

    for rss_source in CONFIG:
        rss_source_name = rss_source['name']
        rss_source_path = rss_source['path']
        rss_source_link = rss_source['rss_link']
        rss_require_date = rss_source.get('require_date', False)
        rss_disable = rss_source.get('disable', False)

        if rss_disable:
            log('Skipping the "{}"', rss_source_name)
            continue

        log('Checking "{}"', rss_source_name)
        missing_files_links = list(build_to_download_list(
            rss_source_path,
            rss_source_link,
            rss_require_date))

        if missing_files_links:
            for rss_entry in reversed(missing_files_links):
                if DOWNLOADS_LIMITS == 0:
                    continue

                log('{}: Downloading file: "{}"', rss_source_name, rss_entry.link)
                download_rss_entity_to_path(rss_source_path, rss_entry)
                DOWNLOADS_LIMITS -= 1
        else:
            log('{}: Nothing new', rss_source_name)
