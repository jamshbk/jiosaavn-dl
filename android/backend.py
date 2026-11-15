"""Mobile adapter inspired by bunnykek/jiosaavn-dl. See ATTRIBUTION.md."""
import html
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlparse, unquote
import requests
from mutagen.mp4 import MP4, MP4Cover
from settings import DEFAULTS
from filenames import track_name

API = 'https://www.jiosaavn.com/api.php'


class Cancelled(Exception):
    pass


def clean(value):
    return html.unescape(str(value or ''))


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', clean(value)).strip(' .')
    return name.encode('utf-8')[:180].decode('utf-8','ignore') or 'Untitled'


def parse_link(url):
    parts = urlparse(url.strip())
    if parts.scheme != 'https' or parts.hostname not in ('www.jiosaavn.com', 'jiosaavn.com'):
        raise ValueError('Paste a valid https://www.jiosaavn.com link.')
    path = [x for x in parts.path.split('/') if x]
    if len(path) < 3:
        raise ValueError('This link is incomplete.')
    if path[0] in ('song', 'album', 'featured'):
        kind = 'playlist' if path[0] == 'featured' else path[0]
    elif len(path) >= 4 and path[:2] == ['s', 'playlist']:
        kind = 'playlist'
    else:
        raise ValueError('Use a song, album or playlist link.')
    return kind, unquote(path[-1])


class Client:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        self.session.mount('https://', HTTPAdapter(max_retries=Retry(
            total=2, backoff_factor=.4, status_forcelist=(429, 502, 503, 504))))

    def api(self, call, **params):
        response = self.session.get(API, params={
            '__call': call, '_format': 'json', '_marker': '0', **params
        }, timeout=(10, 30))
        response.raise_for_status()
        text = response.text.strip()
        try:
            data = response.json()
        except ValueError:
            start, end = text.find('{'), text.rfind('}')
            if start < 0 or end < start:
                raise ValueError('The music service returned an unexpected response.')
            data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            raise ValueError('The music service returned an unexpected response.')
        return data

    def search(self, query, page=1):
        data = self.api('search.getResults', q=query, p=page, n=20)
        songs = data.get('results', [])
        if not isinstance(songs, list):
            raise ValueError('Search response format has changed.')
        return [s for s in songs if isinstance(s, dict) and s.get('perma_url')]

    def resolve(self, link):
        kind, token = parse_link(link)
        data = self.api('webapi.get', token=token, type=kind, n=1000)
        if kind == 'song':
            if data.get('song'):
                songs = [data]
            else:
                songs = [s for s in data.values() if isinstance(s, dict) and s.get('song')]
        else:
            songs = data.get('songs', [])
            count = int(data.get('list_count') or len(songs))
            if count > len(songs):
                raise ValueError('The service returned only part of this playlist. Download smaller playlists or individual tracks.')
        if not songs:
            raise ValueError('No available tracks found for this link.')
        title = songs[0].get('song') if kind == 'song' else data.get('title') or data.get('listname') or songs[0].get('album')
        return {
            'kind': kind, 'title': clean(title),
            'artist': clean(data.get('primary_artists') or songs[0].get('primary_artists')),
            'year': clean(data.get('year') or songs[0].get('year')),
            'image': data.get('image') or songs[0].get('image') or '',
            'songs': songs,
        }

    def media_url(self, song, quality='320'):
        if quality not in ('96', '160', '320'):
            raise ValueError('Unsupported audio quality.')
        if not song.get('encrypted_media_url'):
            raise ValueError('This track is unavailable for download.')
        auth = self.api('song.generateAuthToken', url=song['encrypted_media_url'],
                        bitrate=quality, api_version=4, ctx='web6dot0')
        media_url = auth.get('auth_url')
        if not media_url:
            raise ValueError('The service did not provide a download URL.')
        # Same CDN selection used by the upstream downloader.
        media_url = media_url.replace('web', 'aac', 1)
        parsed = urlparse(media_url)
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or not (host.endswith('.saavncdn.com') or host.endswith('.jiosaavn.com')):
            raise ValueError('The service returned an unsupported audio URL.')
        return media_url

    def download(self, song, directory, cancel, progress, settings=None, number=1, context='single', album_artist=None):
        settings = {**DEFAULTS, **(settings or {})}
        if cancel.is_set():
            raise Cancelled()
        media_url = self.media_url(song, settings['quality'])
        name = track_name(song,settings,number,context,album_artist)
        target = Path(directory) / (name + '.m4a')
        suffix = 2
        while target.exists():
            target = Path(directory) / (name + f' ({suffix}).m4a')
            suffix += 1
        part = target.with_suffix('.part')
        try:
            with self.session.get(media_url, stream=True, timeout=(10, 30)) as response:
                response.raise_for_status()
                total = int(response.headers.get('Content-Length') or 0)
                done = 0
                with part.open('wb') as output:
                    for chunk in response.iter_content(64 * 1024):
                        if cancel.is_set():
                            raise Cancelled()
                        if chunk:
                            output.write(chunk)
                            done += len(chunk)
                            progress(done, total)
                if not done or (total and done != total):
                    raise ValueError('Download was incomplete. Please retry.')
            # Validate the audio before it is published to Downloads.
            audio = MP4(part)
            for key, value in {'\xa9nam': song.get('song'), '\xa9alb': song.get('album'),
                               '\xa9ART': song.get('primary_artists'), '\xa9wrt': song.get('music'),
                               '\xa9day': (song.get('release_date') if settings['original_date'] else None) or song.get('year'),
                               'cprt': song.get('copyright_text')}.items():
                if value:
                    audio[key] = [clean(value)]
            warnings = []
            if settings['explicit_tag']:
                audio['rtng'] = [4 if str(song.get('explicit_content')).lower() in ('1', 'true') else 2]
            audio['trkn'] = [(number, 0)]
            if settings['cover_art'] and song.get('image'):
                try:
                    image_url = song['image'].replace('150x150', '500x500')
                    with self.session.get(image_url, timeout=(10, 20)) as cover:
                        cover.raise_for_status()
                        if cover.content.startswith(b'\xff\xd8'):
                            audio['covr'] = [MP4Cover(cover.content, imageformat=MP4Cover.FORMAT_JPEG)]
                except requests.RequestException:
                    warnings.append('cover unavailable')
            lyrics_text = None
            if (settings['embed_lyrics'] or settings['save_lyrics']) and str(song.get('has_lyrics')).lower() == 'true':
                try:
                    lyrics = self.api('lyrics.getLyrics', lyrics_id=song['id'], api_version=4, ctx='web6dot0')
                    if lyrics.get('lyrics'):
                        lyrics_text = clean(re.sub(r'<br\s*/?>', '\n', lyrics['lyrics']))
                        if settings['embed_lyrics']:
                            audio['\xa9lyr'] = [lyrics_text]
                except (requests.RequestException, ValueError):
                    warnings.append('lyrics unavailable')
            audio.save()
            if cancel.is_set():
                raise Cancelled()
            part.replace(target)
            if settings['save_lyrics'] and lyrics_text:
                target.with_suffix('.txt').write_text(lyrics_text, encoding='utf-8')
            return target, warnings
        finally:
            part.unlink(missing_ok=True)

