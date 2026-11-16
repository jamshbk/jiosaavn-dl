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
    def test_album_search_returns_only_safe_album_links_and_metadata(self):
        client = backend.Client()
        client.api = Mock(return_value={'results':[
            {'title':'Album &amp; One','music':'Artist','year':'2024','perma_url':'https://www.jiosaavn.com/album/one/token'},
            {'title':'Track','perma_url':SONG['perma_url']},
            {'title':'Bad','perma_url':'https://example.com/album/one/token'},
        ]})
        albums=client.search_albums('One',2)
        self.assertEqual([a['title'] for a in albums],['Album & One'])
        self.assertEqual(albums[0]['artist'],'Artist')
        self.assertEqual(client.api.call_count,2)
        self.assertEqual([call.args[0] for call in client.api.call_args_list],['search.getAlbumResults','search.getResults'])

    def test_song_title_finds_its_album_when_album_title_search_is_empty(self):
        client=backend.Client()
        client.api=Mock(side_effect=[{'results':[]},{'results':[{
            'title':'Gerua','year':'2015','more_info':{'album':'Dilwale',
                'album_url':'https://www.jiosaavn.com/album/dilwale/albumToken',
                'artistMap':{'primary_artists':[{'name':'Arijit Singh'}]}}}]}])
        albums=client.search_albums('Gerua')
        self.assertEqual([(a['title'],a['matched_song']) for a in albums],[('Dilwale','Gerua')])
        self.assertEqual(albums[0]['artist'],'Arijit Singh')

    def test_song_linked_albums_are_deduplicated_by_token_and_keep_pagination(self):
        client=backend.Client()
        song={'title':'Track','more_info':{'album':'Real Album','album_url':'https://www.jiosaavn.com/album/real/sameToken'}}
        client.api=Mock(side_effect=[{'results':[{'title':'Real Album','perma_url':'https://jiosaavn.com/album/alias/sameToken'}]},
                                     {'results':[song]*20}])
        self.assertEqual(len(client.search_albums('Track')),1)
        self.assertTrue(client.album_has_more)

    def test_album_title_matches_survive_song_lookup_failure(self):
        client=backend.Client()
        client.api=Mock(side_effect=[{'results':[{'title':'Album','perma_url':'https://www.jiosaavn.com/album/a/token'}]},backend.requests.ConnectionError('offline')])
        self.assertEqual(client.search_albums('Album')[0]['title'],'Album')
        self.assertIn('Song-based',client.album_search_note)

    def test_both_album_sources_failing_is_an_error(self):
        client=backend.Client();client.api=Mock(side_effect=backend.requests.ConnectionError('offline'))
        with self.assertRaisesRegex(ValueError,'temporarily unavailable'):
            client.search_albums('Track')

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
            options = {**DEFAULTS, 'quality':'96', 'single_track_template':'{track}. {title}', 'embed_lyrics':False,
                       'save_lyrics':True, 'explicit_tag':False, 'original_date':False}
            path, notes = client.download(SONG, d, threading.Event(), lambda *_:None, options, 3)
            self.assertEqual(path.name, '03. A & B.m4a')
            self.assertEqual(path.with_suffix('.txt').read_text(), 'First\nSecond')
            self.assertNotIn('\xa9lyr', tags)
            self.assertNotIn('rtng', tags)
            self.assertEqual(tags['\xa9day'], ['2024'])
            self.assertEqual(client.media_url.call_args.args[1], '96')


class ApiTests(unittest.TestCase):
    def test_home_ready_handoff_uses_cached_native_bridge(self):
        ui=Mock()
        with patch.object(main,'ANDROID',True), patch('android_bridge.get_bridge',return_value={'NativeUi':ui}):
            result=self.request('/api/startup/ready',{}).args[0]
            self.assertTrue(result['ok'])
            ui.finishStartup.assert_called_once_with()

    def test_album_search_does_not_mix_in_track_search_results(self):
        with patch.object(main,'Client') as cls:
            cls.return_value.search_albums.return_value=[{'title':'Album','url':'https://www.jiosaavn.com/album/a/t'}]
            result=self.request('/api/archive',{'query':'Artist','search_type':'albums','page':2}).args[0]
            self.assertEqual(result['kind'],'album-search')
            self.assertEqual(result['songs'],[])
            self.assertEqual(len(result['albums']),1)
            cls.return_value.search.assert_not_called()
            cls.return_value.search_albums.assert_called_once_with('Artist',2)

    def test_explicit_zip_works_for_one_song_with_zip_setting_off(self):
        key=main.register([SONG],'An Album','album')[0]['key']
        with tempfile.TemporaryDirectory() as d, patch.object(main,'PREFS',Settings(Path(d)/'prefs.json')), patch.object(main.threading,'Thread') as thread:
            main.PREFS.save({'zip_album':False})
            main.status(active=False)
            try:
                result=self.request('/api/download',{'keys':[key],'bundle':True,'format':'zip'}).args[0]
                self.assertTrue(result['active'])
                self.assertIs(thread.call_args.kwargs['args'][2],True)
            finally:
                main.status(active=False)

    def test_single_song_zip_contains_only_requested_album_track(self):
        record={'song':SONG,'number':1,'collection':'Only This Album','context':'album'}
        def fake_download(song,directory,*args,**kwargs):
            path=Path(directory)/'Only Track.m4a';path.write_bytes(b'audio');return path,[]
        with tempfile.TemporaryDirectory() as d, patch.object(main,'DATA',Path(d)), patch.object(main,'Client') as cls:
            cls.return_value.download.side_effect=fake_download
            main.CANCEL.clear()
            main.download_worker([record],{**DEFAULTS,'zip_album':False},True)
            archives=list((Path(d)/'Downloads').rglob('*.zip'))
            self.assertEqual(len(archives),1)
            with main.zipfile.ZipFile(archives[0]) as archive:
                self.assertEqual(archive.namelist(),['Only This Album/Only Track.m4a'])

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
        def fake_download(song, directory, cancel, progress, options, number, **kwargs):
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
