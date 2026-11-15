import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import backend
import main
from settings import Settings, DEFAULTS, validate


SONG = {'id': 'song123', 'song': 'A &amp; B', 'album': 'An Album',
        'primary_artists': 'An Artist', 'duration': '241', 'year': '2024',
        'perma_url': 'https://www.jiosaavn.com/song/a/token',
        'encrypted_media_url': 'opaque', 'explicit_content': 1,
        'release_date': '2024-02-03', 'has_lyrics': 'true'}


class PreferencesTests(unittest.TestCase):
    def test_persist_reset_and_partial_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'prefs.json'
            prefs = Settings(path)
            prefs.save({'quality': '160', 'save_lyrics': True})
            prefs.save({'folder': 'My Songs'})
            restored = Settings(path).get()
            self.assertEqual(restored['quality'], '160')
            self.assertTrue(restored['save_lyrics'])
            self.assertEqual(restored['folder'], 'My Songs')
            self.assertEqual(prefs.save(reset=True), DEFAULTS)

    def test_invalid_settings_do_not_overwrite(self):
        for patch in [{'quality':'999'}, {'folder':'../escape'}, {'folder':''}, {'embed_lyrics':'false'}]:
            with self.assertRaises(ValueError):
                validate(patch)


class BackendTests(unittest.TestCase):
    def test_preview_resolves_metadata_without_downloading(self):
        client = backend.Client()
        client.api = Mock(return_value={'title':'Album &amp; More', 'songs':[SONG], 'year':'2024'})
        client.download = Mock()
        result = client.resolve('https://www.jiosaavn.com/album/name/token')
        self.assertEqual(result['kind'], 'album')
        self.assertEqual(result['title'], 'Album & More')
        self.assertEqual(result['songs'][0]['id'], 'song123')
        client.download.assert_not_called()

    def test_partial_playlist_is_not_silent(self):
        client = backend.Client()
        client.api = Mock(return_value={'listname':'Mix', 'songs':[SONG], 'list_count':20})
        with self.assertRaisesRegex(ValueError, 'part of this playlist'):
            client.resolve('https://www.jiosaavn.com/featured/mix/token')

    def test_quality_changes_auth_request(self):
        client = backend.Client()
        client.api = Mock(return_value={'auth_url':'https://aac.saavncdn.com/example.m4a'})
        client.media_url(SONG, '160')
        self.assertEqual(client.api.call_args.kwargs['bitrate'], '160')
        client.api.return_value = {'auth_url':'https://evil.invalid/private'}
        with self.assertRaises(ValueError):
            client.media_url(SONG, '96')

    def test_cancellation_leaves_no_partial_file(self):
        client = backend.Client()
        client.media_url = Mock(return_value='https://aac.saavncdn.com/song.m4a')
        response = Mock()
        response.headers = {'Content-Length':'6'}
        cancel = threading.Event()
        def chunks(_):
            yield b'abc'
            cancel.set()
            yield b'def'
        response.iter_content.side_effect = chunks
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        client.session.get = Mock(return_value=context)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(backend.Cancelled):
                client.download(SONG, d, cancel, lambda *_:None)
            self.assertFalse(list(Path(d).iterdir()))

    def test_settings_change_tags_names_and_sidecar(self):
        client = backend.Client()
        client.media_url = Mock(return_value='https://aac.saavncdn.com/song.m4a')
        client.api = Mock(return_value={'lyrics':'First<br>Second'})
        response = Mock(headers={'Content-Length':'3'})
        response.iter_content.return_value = iter([b'abc'])
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        client.session.get = Mock(return_value=context)
        class Tags(dict):
            def save(self):
                pass
        tags = Tags()
        with tempfile.TemporaryDirectory() as d, patch.object(backend, 'MP4', return_value=tags):
            options = {**DEFAULTS, 'quality':'96', 'naming':'track_title', 'embed_lyrics':False,
                       'save_lyrics':True, 'explicit_tag':False, 'original_date':False}
            path, notes = client.download(SONG, d, threading.Event(), lambda *_:None, options, 3)
            self.assertEqual(path.name, '03. A & B.m4a')
            self.assertEqual(path.with_suffix('.txt').read_text(), 'First\nSecond')
            self.assertNotIn('\xa9lyr', tags)
            self.assertNotIn('rtng', tags)
            self.assertEqual(tags['\xa9day'], ['2024'])
            self.assertEqual(client.media_url.call_args.args[1], '96')


class ApiTests(unittest.TestCase):
    def request(self, path, data, token=None):
        handler = main.Handler.__new__(main.Handler)
        content = json.dumps(data).encode()
        handler.headers = {'Host':'127.0.0.1:5000', 'X-App-Token':main.TOKEN if token is None else token,
                           'Content-Length':str(len(content))}
        handler.server = SimpleNamespace(server_port=5000)
        handler.rfile = io.BytesIO(content)
        handler.path = path
        handler.respond = Mock()
        handler.do_POST()
        return handler.respond.call_args

    def test_archive_only_previews_and_escapes_at_render_boundary(self):
        with patch.object(main, 'Client') as cls:
            cls.return_value.resolve.return_value = {'kind':'album','title':'Example','songs':[SONG]}
            args = self.request('/api/archive', {'query':'https://www.jiosaavn.com/album/name/token'})
            result = args.args[0]
            self.assertEqual(result['songs'][0]['title'], 'A & B')
            self.assertNotIn('encrypted_media_url', result['songs'][0])
            cls.return_value.download.assert_not_called()

    def test_requires_session_token(self):
        args = self.request('/api/archive', {'query':'Test'}, token='wrong')
        self.assertEqual(args.args[1], 403)

    def test_player_uses_selected_quality(self):
        key = main.register([SONG])[0]['key']
        with patch.object(main, 'Client') as cls:
            cls.return_value.media_url.return_value='https://aac.saavncdn.com/song.m4a'
            args=self.request('/api/play', {'key':key,'quality':'160'})
            self.assertEqual(args.args[0]['quality'], '160')
            self.assertEqual(cls.return_value.media_url.call_args.args[1], '160')

    def test_selected_tracks_download_and_zip_layout(self):
        record={'song':SONG,'number':1,'collection':'Example Album'}
        def fake_download(song, directory, cancel, progress, options, number):
            path=Path(directory)/('A.m4a' if not (Path(directory)/'A.m4a').exists() else 'B.m4a');path.write_bytes(b'audio')
            path.with_suffix('.txt').write_text('Lyrics')
            return path, []
        with tempfile.TemporaryDirectory() as d, patch.object(main,'DATA',Path(d)), patch.object(main,'Client') as cls:
            cls.return_value.download.side_effect=fake_download
            main.CANCEL.clear()
            main.download_worker([record,record], {**DEFAULTS,'zip_album':True,'disc_folders':True}, True)
            archives=list((Path(d)/'Downloads').rglob('*.zip'))
            self.assertEqual(len(archives),1)
            with main.zipfile.ZipFile(archives[0]) as z:
                self.assertIn('Example Album/Disc 1/A.m4a',z.namelist())
                self.assertIn('Example Album/Disc 1/A.txt',z.namelist())
            self.assertFalse(main.snapshot()['active'])


if __name__ == '__main__':
    unittest.main()
