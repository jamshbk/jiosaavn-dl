"""Mobile adapter inspired by bunnykek/jiosaavn-dl. See ATTRIBUTION.md."""
import html
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlparse, unquote
import requests
from mutagen.mp4 import MP4, MP4Cover

API = 'https://www.jiosaavn.com/api.php'


class Cancelled(Exception):
    pass


def clean(value):
    return html.unescape(str(value or ''))


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', clean(value)).strip(' .')
    return name[:110] or 'Untitled'


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
        return songs

    def download(self, song, directory, cancel, progress):
        if cancel.is_set():
            raise Cancelled()
        if not song.get('encrypted_media_url'):
            raise ValueError('This track is unavailable for download.')
        auth = self.api('song.generateAuthToken', url=song['encrypted_media_url'],
                        bitrate='320', api_version=4, ctx='web6dot0')
        media_url = auth.get('auth_url')
        if not media_url:
            raise ValueError('The service did not provide a download URL.')
        # Same CDN selection used by the upstream downloader.
        media_url = media_url.replace('web', 'aac', 1)
        target = Path(directory) / (safe_name(song.get('song')) + ' - ' + safe_name(song.get('id')) + '.m4a')
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
                               '\xa9day': song.get('release_date') or song.get('year'),
                               'cprt': song.get('copyright_text')}.items():
                if value:
                    audio[key] = [clean(value)]
            warnings = []
            if song.get('image'):
                try:
                    image_url = song['image'].replace('150x150', '500x500')
                    with self.session.get(image_url, timeout=(10, 20)) as cover:
                        cover.raise_for_status()
                        if cover.content.startswith(b'\xff\xd8'):
                            audio['covr'] = [MP4Cover(cover.content, imageformat=MP4Cover.FORMAT_JPEG)]
                except requests.RequestException:
                    warnings.append('cover unavailable')
            if str(song.get('has_lyrics')).lower() == 'true':
                try:
                    lyrics = self.api('lyrics.getLyrics', lyrics_id=song['id'], api_version=4, ctx='web6dot0')
                    if lyrics.get('lyrics'):
                        audio['\xa9lyr'] = [clean(re.sub(r'<br\s*/?>', '\n', lyrics['lyrics']))]
                except (requests.RequestException, ValueError):
                    warnings.append('lyrics unavailable')
            audio.save()
            if cancel.is_set():
                raise Cancelled()
            part.replace(target)
            return target, warnings
        finally:
            part.unlink(missing_ok=True)
