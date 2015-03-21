import codecs
import logging
import re
from glob import iglob
from os.path import join, dirname, normpath

from gevent import monkey
from gevent.event import AsyncResult
from gevent.pool import Pool
monkey.patch_socket()
monkey.patch_ssl()

import requests
from lxml import html
from mutagen import easyid3, flac, easymp4, oggvorbis, musepack
from wikiapi import WikiApi


logger = logging.getLogger(__name__)

URI_SCHEME = 'http'
ARTICLE_URI = 'wikipedia.org/wiki/'
GENRE_CACHE = {}  # {(album, artist): AsyncResult([genre1, genre2, ...])}


class SetFile(set):
    def __init__(self, filename):
        try:
            with codecs.open(filename, 'r', encoding='utf-8') as fp:
                lines = fp.read().splitlines()
        except IOError:
            lines = []
        super(SetFile, self).__init__(lines)
        self.fp = codecs.open(filename, 'a', encoding='utf-8')

    def add(self, value):
        super(SetFile, self).add(value)
        self.fp.write(value)
        self.fp.write(u'\n')
        self.fp.flush()

    def close(self):
        self.fp.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return self.fp.__exit__(*exc_info)


def titlecase(string):
    return u' '.join(part.capitalize() for part in string.split())


def get_genres(query):
    wiki = WikiApi()
    results = wiki.find(query.encode('utf-8'))
    if results:
        try:
            url = '{0}://{1}.{2}{3}'.format(
                URI_SCHEME, wiki.options['locale'], ARTICLE_URI,
                results[0].encode('utf-8'))
            resp = requests.get(url)
            dom = html.fromstring(resp.content)
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
    return []


def search_variants(artist, album):
    if artist and album:
        yield get_genres(u'%s (%s album)' % (album, artist))
    if album:
        yield get_genres(u'%s (album)' % album)
        yield get_genres(album)
    if artist:
        yield get_genres(artist)


def albumgenres(artist='', album=''):
    result = GENRE_CACHE.get((artist, album))
    if result is None:
        result = AsyncResult()
        GENRE_CACHE[(artist, album)] = result
        result.set(reduce(lambda a, b: a or b, search_variants(artist, album)))
    return result.get()


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


def wikigenre(track, force=False):
    track = normpath(track)
    try:
        audio = load_track(track)
        audio_genre = audio.get('genre')
        if audio_genre is not None and not force:
            logger.info('Skipping %s', track)
        else:
            artist = audio.get('artist', [None])[0]
            album = audio.get('album', [None])[0]
            genres = map(titlecase, albumgenres(artist, album))
            if genres:
                audio['genre'] = genres
                audio.save()
                logger.info('Tagged %s', track)
            else:
                logger.warn('No genres found for %s', track)
    except Exception as e:
        logger.error('Error tagging %s: %s', track, repr(e))
        raise


def main(string='', path=None, force=False):
    with open(join(dirname(__file__), 'wikigenre.log'), 'a') as log:
        handler = logging.StreamHandler()
        filehandler = logging.StreamHandler(log)

        formatter = logging.Formatter('%(asctime)s;%(levelname)s;%(message)s')

        handler.setFormatter(formatter)
        filehandler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.addHandler(filehandler)

        logger.setLevel('DEBUG')

        if string:
            for artistalbum in string.split('; '):
                parts = artistalbum.split(' - ', 1)
                try:
                    artist, album = parts
                except ValueError:
                    artist, album = '', artistalbum
                print (artistalbum + ': ' +
                       '; '.join(map(titlecase, albumgenres(artist, album))))
        else:
            logger.info('Starting')
            # Escape square brackets
            path = re.sub(r'([\[\]])', r'[\1]', path)
            pool = Pool(8)
            for track in iglob(path):
                pool.spawn(wikigenre, track, force=force)
            pool.join()
            logger.info('Finished')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('path', metavar='PATH', nargs='?')
    parser.add_argument('--string', metavar='STRING', nargs='?', default='',
                        help='[artist - ]album(; [artist - ]album)*')
    parser.add_argument('-f', '--force', action='store_true')
    namespace = parser.parse_args()
    kwargs = dict(namespace._get_kwargs())

    main(**kwargs)
