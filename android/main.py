"""Local-only WebView application server. Run `python main.py` for desktop preview."""
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from backend import Client, Cancelled, clean, safe_name
from settings import Settings
from storage import publish
from filenames import render_name

ANDROID = 'ANDROID_ARGUMENT' in os.environ
ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('SAAVN_DATA_DIR', str(ROOT / 'appdata')))
DATA.mkdir(parents=True, exist_ok=True)
PREFS = Settings(DATA / 'settings.json')
TOKEN = secrets.token_urlsafe(32)
CATALOG = {}
LOCK = threading.RLock()
CANCEL = threading.Event()
JOB = {'active': False, 'message': 'Ready.', 'progress': 0, 'saved': 0,
       'failed': 0, 'errors': [], 'warnings': [], 'destination': ''}


def register(songs, collection='', kind='search', album_artist=''):
    result = []
    discs={str(s.get('disc_number') or s.get('disc') or '1').split('/')[0] for s in songs}
    multi=len(discs)>1 or any(d.isdigit() and int(d)>1 for d in discs)
    counters={}
    with LOCK:
        if len(CATALOG) > 2000 and not JOB['active']:
            CATALOG.clear()
        for number, song in enumerate(songs, 1):
            song=dict(song)
            disc=str(song.get('disc_number') or song.get('disc') or '1').split('/')[0]
            song['disc_number']=disc if disc.isdigit() and int(disc)>0 else '1'
            counters[disc]=counters.get(disc,0)+1
            file_number=counters[disc] if multi else number
            key = secrets.token_hex(8)
            context='single' if kind in ('song','search') else 'multidisc' if multi else 'album'
            CATALOG[key] = {'song': song, 'number': file_number, 'collection': collection,
                            'context':context,'album_artist':album_artist}
            duration = int(song.get('duration') or 0)
            result.append({'key': key, 'title': clean(song.get('song') or song.get('title')),
                           'artist': clean(song.get('primary_artists')),
                           'album': clean(song.get('album')), 'year': clean(song.get('year')),
                           'image': song.get('image') or '', 'duration': duration,
                           'language': clean(song.get('language')), 'number': number})
    return result


def status(**values):
    with LOCK:
        JOB.update(values)


def snapshot():
    with LOCK:
        return json.loads(json.dumps(JOB))


def download_worker(records, options, bundle):
    work = Path(tempfile.mkdtemp(prefix='download-', dir=DATA))
    client = Client()
    saved, errors, warnings = 0, [], []
    exported = []
    ready = []
    try:
        for index, record in enumerate(records, 1):
            if CANCEL.is_set():
                raise Cancelled()
            song = record['song']
            title = clean(song.get('song'))
            folder = ''
            if options['album_folders']:
                folder = safe_name(record['collection'] or song.get('album'))
            if options['disc_folders']:
                folder = str(Path(folder) / ('Disc ' + safe_name(song.get('disc_number') or '1')))
            directory = work / folder
            directory.mkdir(parents=True, exist_ok=True)
            last = [0.0]
            def progress(done, total):
                now = time.monotonic()
                if now - last[0] < .2 and done != total:
                    return
                last[0] = now
                percent = done / total if total else 0
                status(message=f'{index}/{len(records)} · {title}',
                       detail=f'{done / 1048576:.1f} MB' + (f' / {total / 1048576:.1f} MB' if total else ''),
                       progress=((index - 1 + percent) / len(records) * 100))
            try:
                path, notes = client.download(song, directory, CANCEL, progress, options, record['number'],
                                               context=record.get('context','single'), album_artist=record.get('album_artist'))
                if CANCEL.is_set():
                    raise Cancelled()
                warnings.extend([title + ': ' + n for n in notes])
                files = [path]
                if path.with_suffix('.txt').exists():
                    files.append(path.with_suffix('.txt'))
                if bundle:
                    ready.extend(files)
                else:
                    for item in files:
                        exported.append(export(item, options['folder'], folder))
                saved += 1
            except Cancelled:
                raise
            except Exception as error:
                errors.append(f'{title}: {error}')
            status(saved=saved, failed=len(errors), errors=errors[-20:], warnings=warnings[-20:])
        if CANCEL.is_set():
            raise Cancelled()
        if bundle and ready:
            status(message='Preparing ZIP archive…')
            first=records[0]
            name=render_name(options['album_zip_template'],first['song'],album_artist=first.get('album_artist'),
                             album_name=first['collection'] or first['song'].get('album'))
            archive = work / (name + '.zip')
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
                for item in ready:
                    z.write(item, item.relative_to(work))
            exported.append(export(archive, options['folder'], ''))
        message = f'Saved {saved} song' + ('' if saved == 1 else 's') + '.'
        if errors:
            message += f' {len(errors)} failed — see details.'
        if not saved:
            message = 'No songs were saved. See the error details below.'
        status(message=message, progress=100 if saved else 0,
               destination=options.get('_destination','Downloads/' + options['folder']) if exported else '')
    except Cancelled:
        status(message='Cancelled. Already exported files are kept.',
               destination=options.get('_destination','Downloads/' + options['folder']) if exported else '')
    except Exception as error:
        errors.append(str(error))
        status(message='Could not finish saving. See details.', errors=errors[-20:])
    finally:
        # Retain staged complete files if export failed, for recovery.
        if errors and any(work.rglob('*.m4a')):
            warnings.append('Some files remain in private app storage after a save failure.')
        else:
            shutil.rmtree(work, ignore_errors=True)
        status(active=False, saved=saved, failed=len(errors), errors=errors[-20:], warnings=warnings[-20:])


def export(path, folder, subfolder):
    if ANDROID:
        return publish(path, True, folder, subfolder)
    destination = DATA / 'Downloads' / folder / subfolder / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    index = 2
    while destination.exists():
        destination = destination.with_name(f'{path.stem} ({index}){path.suffix}')
        index += 1
    shutil.move(str(path), destination)
    return str(destination)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, data, code=200, mime='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if mime.startswith('application/json') else data
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if host not in allowed:
            self.respond({'error': 'Invalid host.'}, 403)
            return False
        supplied = self.headers.get('X-App-Token', '')
        if not secrets.compare_digest(supplied, TOKEN):
            self.respond({'error': 'Please reopen the app.'}, 403)
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            page = (ROOT / 'web/index.html').read_text(encoding='utf-8').replace('__APP_TOKEN__', TOKEN)
            if ANDROID:
                page = page.replace('<html lang="en">', '<html lang="en" class="native-startup">')
            return self.respond(page.encode(), mime='text/html; charset=utf-8')
        if path in ('/assets/style.css', '/assets/app.js'):
            name = path.rsplit('/', 1)[-1]
            return self.respond((ROOT / 'web' / name).read_bytes(),
                                mime='text/css' if name.endswith('css') else 'application/javascript')
        if path=='/assets/logo.png':
            return self.respond((ROOT/'web/logo.png').read_bytes(),mime='image/png')
        if not self.authorized():
            return
        if path == '/api/settings':
            return self.respond(PREFS.get())
        if path == '/api/job':
            return self.respond(snapshot())
        if path == '/api/destination':
            if ANDROID:
                from storage import get_destination
                return self.respond(get_destination())
            return self.respond({'uri':'','label':'Downloads','path':'Downloads','pending':False,'error':'','desktop':True})
        if path == '/api/device':
            if ANDROID:
                from android_bridge import get_bridge
                return self.respond(json.loads(str(get_bridge()['NativeUi'].getLayoutMetrics())))
            return self.respond({})
        if path == '/api/startup':
            if ANDROID:
                from android_bridge import get_bridge
                return self.respond(json.loads(str(get_bridge()['NativeUi'].getStartupStats())))
            return self.respond({})
        return self.respond({'error': 'Not found.'}, 404)

    def do_POST(self):
        if not self.authorized():
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 65536:
                raise ValueError('Request is too large.')
            body = json.loads(self.rfile.read(length) or '{}')
            if not isinstance(body, dict):
                raise ValueError('Invalid request.')
            path = urlparse(self.path).path
            if path == '/api/startup/ready':
                if ANDROID:
                    from android_bridge import get_bridge
                    get_bridge()['NativeUi'].finishStartup()
                return self.respond({'ok': True})
            if path == '/api/settings':
                return self.respond(PREFS.save(body.get('patch'), reset=body.get('reset') is True))
            if path == '/api/archive':
                query = str(body.get('query') or '').strip()
                if not query or len(query) > 2000:
                    raise ValueError('Enter a song name, artist or JioSaavn link.')
                client = Client()
                if '://' in query or query.startswith('www.'):
                    if query.startswith('www.'):
                        query = 'https://' + query
                    info = client.resolve(query)
                    info['songs'] = register(info['songs'], info['title'] if info['kind'] != 'song' else '',info['kind'],info.get('artist',''))
                    return self.respond(info)
                page = max(1, min(int(body.get('page') or 1), 500))
                search_type = body.get('search_type', 'tracks')
                if search_type not in ('tracks', 'albums'):
                    raise ValueError('Choose Tracks or Albums.')
                if search_type == 'albums':
                    return self.respond({'kind': 'album-search', 'title': query,
                                         'albums': client.search_albums(query, page), 'songs': [], 'page': page})
                songs = register(client.search(query, page))
                return self.respond({'kind': 'search', 'title': query, 'songs': songs, 'page': page})
            if path == '/api/clipboard':
                if not ANDROID:
                    raise ValueError('Please paste with your keyboard or browser clipboard.')
                from android_bridge import read_clipboard
                return self.respond({'text': read_clipboard()})
            if path in ('/api/folder/pick','/api/folder/default'):
                if not ANDROID:
                    raise ValueError('The Android folder picker is available on the phone app.')
                with LOCK:
                    if JOB['active']:
                        raise ValueError('Wait for the current download to finish before changing folders.')
                from storage import choose_destination, reset_destination
                return self.respond(choose_destination() if path.endswith('/pick') else reset_destination())
            if path=='/api/native-check-folder':
                if not ANDROID:
                    return self.respond({'error':'Not found.'},404)
                from android_bridge import get_bridge
                bridge=get_bridge()
                if not bridge['activity'].getIntent().getBooleanExtra('saavn_native_test',False):
                    return self.respond({'error':'Not found.'},404)
                return self.respond({'ok':bool(bridge['NativeUi'].checkCustomFolder())})
            if path == '/api/play':
                with LOCK:
                    record = CATALOG.get(body.get('key'))
                if not record:
                    raise ValueError('Search or open this song again.')
                quality = str(body.get('quality') or PREFS.get()['quality'])
                return self.respond({'url': Client().media_url(record['song'], quality), 'quality': quality})
            if path == '/api/cancel':
                CANCEL.set()
                return self.respond({'ok': True})
            if path == '/api/download':
                keys = body.get('keys')
                if not isinstance(keys, list) or not keys or len(keys) > 1000 or any(not isinstance(k, str) for k in keys):
                    raise ValueError('Choose at least one song.')
                with LOCK:
                    if JOB['active']:
                        return self.respond({'error': 'A download is already running.'}, 409)
                    records = [CATALOG.get(key) for key in dict.fromkeys(keys)]
                    if not all(records):
                        raise ValueError('Some results expired. Open the album again.')
                    options = PREFS.get()
                    if ANDROID:
                        from storage import get_destination
                        destination=get_destination()
                        options['_destination']=destination.get('path',destination['label']) if destination.get('uri') else 'Downloads/'+options['folder']
                    output_format = body.get('format')
                    if output_format not in (None, 'zip'):
                        raise ValueError('Unsupported download format.')
                    bundle = output_format == 'zip' or (len(records) > 1 and body.get('bundle') is True and options['zip_album'])
                    CANCEL.clear()
                    status(active=True, message='Starting download…', progress=0, saved=0,
                           failed=0, errors=[], warnings=[], destination='', detail='')
                    threading.Thread(target=download_worker, args=(records, options, bundle), daemon=True).start()
                return self.respond(snapshot())
            return self.respond({'error': 'Not found.'}, 404)
        except Exception as error:
            return self.respond({'error': str(error)[:400]}, 400)


if __name__ == '__main__':
    if ANDROID:
        try:
            from android_bridge import initialize
            bridge = initialize()
            if bridge['activity'].getIntent().getBooleanExtra('saavn_native_test', False):
                from storage import native_storage_check
                native_storage_check(DATA)
                print('SAAVN_NATIVE_CHECK_OK', flush=True)
        except Exception as error:
            print('SAAVN_NATIVE_CHECK_FAILED: ' + str(error), flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('SAAVN_PORT', '5000'))), Handler)
    server.daemon_threads = True
    server.serve_forever()
