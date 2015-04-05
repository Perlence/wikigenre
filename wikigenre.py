from asyncio import async, coroutine, get_event_loop, wait
import logging
import re
import sys
from glob import iglob
from os.path import join, dirname, normpath
import urllib.parse
from xml.dom import minidom

from aiohttp import request
from lxml import html
from mutagen import easyid3, flac, easymp4, oggvorbis, musepack
from wikiapi import WikiApi


logger = logging.getLogger(__name__)

URI_SCHEME = 'http'
API_URI = 'wikipedia.org/w/api.php'
ARTICLE_URI = 'wikipedia.org/wiki/'

genre_cache = {}  # {(album, artist): Task([genre1, genre2, ...])}


class AsyncWikiApi(WikiApi):
    @coroutine
    def find(self, terms):
        search_params = {
            'action': 'opensearch',
            'search': terms,
            'format': 'xml'
        }
        url = self.build_url(search_params)
        resp = yield from self.get(url)

        # parse search results
        xmldoc = minidom.parseString(resp)
        items = xmldoc.getElementsByTagName('Item')

        # return results as wiki page titles
        results = []
        for item in items:
            link = item.getElementsByTagName('Url')[0].firstChild.data
            slug = re.findall(r'wiki/(.+)', link, re.IGNORECASE)
            results.append(slug[0])
        return results

    @coroutine
    def get(self, url):
        if self.caching_enabled:
            cached_item_path = self._get_cache_item_path(url)
            cached_resp = self._get_cached_response(cached_item_path)
            if cached_resp:
                return cached_resp

        r = yield from request('GET', url)
        response = yield from r.text()

        if self.caching_enabled:
            self._cache_response(cached_item_path, response)

        return response

    def build_url(self, params):
        default_params = {'format': 'xml'}
        query_params = dict(
            list(default_params.items()) + list(params.items()))
        query_params = urllib.parse.urlencode(query_params)
        return '{0}://{1}.{2}?{3}'.format(
            URI_SCHEME, self.options['locale'], API_URI, query_params)


def titlecase(string):
    return u' '.join(part.capitalize() for part in string.split())


@coroutine
def get_genres(query):
    wiki = AsyncWikiApi()
    results = yield from wiki.find(query.encode('utf-8'))
    if not results:
        return []
    try:
        url = '{0}://{1}.{2}{3}'.format(
            URI_SCHEME, wiki.options['locale'], ARTICLE_URI, results[0])
        resp = yield from request('GET', url)
        text = yield from resp.text()
        dom = html.fromstring(text)
        return (dom.xpath('.'
                          '//table[contains(@class, "haudio")]'
                          '//td[@class="category"]'
                          '/a'
                          '/text()') or
                dom.xpath('.'
                          '//table[contains(@class, "infobox")]'
                          '//th'
                          '/a[text()="Genre"]'
                          '/..'
                          '/..'
                          '/td'
                          '/a'
                          '/text()'))
    except Exception as e:
        logger.error('Error getting genres for %s: %s', query, repr(e))


@coroutine
def search_variants(artist, album):
    genres = []
    if artist and album:
        genres = yield from get_genres(u'%s (%s album)' % (album, artist))
        if genres:
            return genres
    if album:
        genres = yield from get_genres(u'%s (album)' % album)
        if genres:
            return genres
        genres = yield from get_genres(album)
        if genres:
            return genres
    if artist:
        genres = yield from get_genres(artist)
        if genres:
            return genres
    return genres


@coroutine
def albumgenres(artist='', album=''):
    task = genre_cache.get((artist, album))
    if task is None:
        task = async(search_variants(artist, album))
        genre_cache[(artist, album)] = task
    while not task.done():
        yield
    return task.result()


def load_track(track):
    track_lower = track.lower()
    if track_lower.endswith('.mp3'):
        return easyid3.EasyID3(track)
    elif track_lower.endswith('.flac'):
        return flac.FLAC(track)
    elif track_lower.endswith('.mp4') or track_lower.endswith('.m4a'):
        return easymp4.EasyMP4(track)
    elif track_lower.endswith('.ogg'):
        return oggvorbis.OggVorbis(track)
    elif track_lower.endswith('.mpc'):
        return musepack.Musepack(track)
    else:
        raise ValueError("unhandled format '%s'" % track)


@coroutine
def tag_track(track, force=False):
    track = normpath(track)
    try:
        audio = load_track(track)
        audio_genre = audio.get('genre')
        if audio_genre is not None and not force:
            logger.info('Skipping %s', track)
        else:
            artist = audio.get('artist', [None])[0]
            album = audio.get('album', [None])[0]
            genres = map(titlecase, (yield from albumgenres(artist, album)))
            if genres:
                audio['genre'] = genres
                audio.save()
                logger.info('Tagged %s', track)
            else:
                logger.warn('No genres found for %s', track)
    except Exception as e:
        logger.error('Error tagging %s: %s', track, repr(e))


@coroutine
def modes(query, path, force, logger):
    if query:
        for artistalbum in query.split('; '):
            parts = artistalbum.split(' - ', 1)
            try:
                artist, album = parts
            except ValueError:
                artist, album = '', artistalbum
            genres = yield from albumgenres(artist, album)
            print(artistalbum + ': ' +
                  '; '.join(map(titlecase, genres)))
    elif path is not None:
        logger.info('Starting')
        # Escape square brackets
        path = re.sub(r'([\[\]])', r'[\1]', path)
        yield from wait([tag_track(track, force=force)
                         for track in iglob(path)])
        logger.info('Finished')
    else:
        # Read data from stdin
        # Sample input: "The Beatles - [Abbey Road #07] Here Comes the Sun"
        trackinfo = re.compile(
            r'(.+) - \[(.+?)(?: CD\d+)?(?: #\d+)?\]')
        lines = sys.stdin.read()

        @coroutine
        def get_genres_for_track(line):
            mo = trackinfo.match(line)
            if mo is None:
                return
            artist, album = mo.groups()
            return (yield from albumgenres(artist, album))

        tasks = [async(get_genres_for_track(line))
                 for line in lines.splitlines()]
        yield from wait(tasks)
        for task in tasks:
            print('; '.join(map(titlecase, task.result())))


def parse_args():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('path', metavar='PATH', nargs='?',
                        help="path to audio files, can contain wildcards")
    parser.add_argument('-q', '--query',
                        metavar='QUERY', nargs='?', default='',
                        help='fetch genres for given albums\n'
                             '[artist - ]album(; [artist - ]album)*')
    parser.add_argument('-f', '--force', action='store_true',
                        help='rewrite genres even if track already has them')
    return parser.parse_args()


def main():
    namespace = parse_args()
    query = namespace.query
    path = namespace.path
    force = namespace.force

    with open(join(dirname(__file__), 'wikigenre.log'), 'a') as log:
        handler = logging.StreamHandler()
        filehandler = logging.StreamHandler(log)

        formatter = logging.Formatter('%(asctime)s;%(levelname)s;%(message)s')

        handler.setFormatter(formatter)
        filehandler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.addHandler(filehandler)

        logger.setLevel('DEBUG')

        loop = get_event_loop()
        loop.run_until_complete(modes(query, path, force, logger))


if __name__ == '__main__':
    main()
