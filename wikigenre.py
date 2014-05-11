import logging
import codecs

from gevent import monkey
from gevent.pool import Pool
monkey.patch_socket()
monkey.patch_ssl()

import requests
from wikiapi import WikiApi
from mutagen import easyid3, flac, easymp4, oggvorbis, musepack
from lxml import html

import albums


logger = logging.getLogger(__name__)
pool = Pool(8)

uri_scheme = 'http'
api_uri = 'wikipedia.org/w/api.php'
article_uri = 'wikipedia.org/wiki/'

PATH = 'm:\\music'


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
                uri_scheme, wiki.options['locale'], article_uri,
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
    return reduce(lambda a, b: a or b, search_variants(artist, album))


def load_track(track):
    if track.lower().endswith('.mp3'):
        return easyid3.EasyID3(track)
    elif track.lower().endswith('.flac'):
        return flac.FLAC(track)
    elif track.lower().endswith('.mp4') or track.lower().endswith('.m4a'):
        return easymp4.EasyMP4(track)
    elif track.lower().endswith('.ogg'):
        return oggvorbis.OggVorbis(track)
    elif track.lower().endswith('.mpc'):
        return musepack.Musepack(track)
    else:
        raise ValueError("unhandled format '%s'" % track)


def update_genre(track, genres):
    values = map(titlecase, genres)
    audio = load_track(track)
    audio['genre'] = values
    audio.save()


def has_genre(track):
    audio = load_track(track)
    return bool(audio.get('genre'))


def wikigenre(item):
    artist = item['artist']
    album = item['album'].split(None, 1)[-1]
    tracks = item['tracks']()
    try:
        if has_genre(tracks[-1]):
            logger.info('Skipping %s', item['path'])
            return
        genres = albumgenres(artist, album)
        if genres:
            for track in tracks:
                update_genre(track, genres)
            logger.info('Tagged %s', item['path'])
        else:
            logger.warn('No genres found for %s', item['path'])
    except Exception as e:
        logger.error('Error tagging %s: %s', item['path'], repr(e))
        raise


def main(string=''):
    with open('wikigenre.log', 'a') as log:
        handler = logging.StreamHandler(log)
        formatter = logging.Formatter('%(asctime)s;%(levelname)s;%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel('INFO')

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
            for item in albums.albums(PATH):
                pool.spawn(wikigenre, item)
            pool.join()
            logger.info('Finished')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('string', metavar='STRING', nargs='?', default='',
                        help='[artist - ]album(; [artist - ]album)*')
    namespace = parser.parse_args()
    kwargs = dict(namespace._get_kwargs())

    main(**kwargs)
