import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import android_bridge
import storage


class Values(dict):
    def put(self, key, value):
        self[key] = value


class Output(io.BytesIO):
    def close(self):
        self.closed_by_java = True


class Channel:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
    def size(self):
        return len(self.data)
    def transferTo(self, position, size, output):
        data = self.data[position:position + size]
        output.write(data)
        return len(data)


class FileInput:
    def __init__(self, path):
        self.channel = Channel(path)
    def getChannel(self):
        return self.channel
    def close(self):
        pass


class Resolver:
    def __init__(self):
        self.outputs = {}
        self.inserted = []
        self.deleted = []
        self.published = []
    def insert(self, collection, values):
        uri = 'content://downloads/' + str(len(self.inserted))
        self.inserted.append(dict(values))
        return uri
    def openOutputStream(self, uri):
        self.outputs[uri] = Output()
        return self.outputs[uri]
    def openInputStream(self, uri):
        data = iter(self.outputs[uri].getvalue())
        return SimpleNamespace(read=lambda: next(data, -1), close=lambda: None)
    def update(self, uri, values, *_):
        self.published.append((uri, dict(values)))
    def delete(self, uri, *_):
        self.deleted.append(uri)


class AndroidBridgeTests(unittest.TestCase):
    def setUp(self):
        self.resolver = Resolver()
        self.clipboard = Mock()
        self.clipboard.getPrimaryClip.return_value = None
        self.activity = SimpleNamespace(getContentResolver=lambda:self.resolver,
                                        getSystemService=lambda _:self.clipboard)
        self.lookups = []
        def autoclass(name):
            if threading.current_thread() is not threading.main_thread():
                raise RuntimeError('ClassNotFoundException: worker used boot class loader')
            self.lookups.append(name)
            return {
                'org.kivy.android.PythonActivity': SimpleNamespace(mActivity=self.activity),
                'android.content.ContentValues': Values,
                'android.provider.MediaStore$Downloads': SimpleNamespace(EXTERNAL_CONTENT_URI='content://downloads'),
                'java.lang.Integer': int,
                'java.io.FileInputStream': FileInput,
                'java.nio.channels.Channels': SimpleNamespace(newChannel=lambda stream:stream),
            }[name]
        self.patches = [patch.object(android_bridge,'_bridge',None),
                        patch.object(android_bridge,'_error',''),
                        patch.dict(sys.modules,{'jnius':SimpleNamespace(autoclass=autoclass)})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def run_worker(self, function):
        results, errors = [], []
        def target():
            try:
                results.append(function())
            except Exception as error:
                errors.append(error)
        thread=threading.Thread(target=target)
        thread.start();thread.join(3)
        self.assertFalse(thread.is_alive())
        if errors:
            raise errors[0]
        return results[0]

    def test_worker_export_uses_preloaded_activity_and_classes(self):
        android_bridge.initialize()
        lookups = list(self.lookups)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'song.m4a';path.write_bytes(b'complete audio')
            result=self.run_worker(lambda:storage.publish(path,True,'Music','Album'))
            self.assertEqual(result,'Download/Music/Album/song.m4a')
            self.assertFalse(path.exists())
        self.assertEqual(self.lookups,lookups)
        self.assertEqual(next(iter(self.resolver.outputs.values())).getvalue(),b'complete audio')
        self.assertEqual(self.resolver.inserted[0]['is_pending'],1)
        self.assertEqual(self.resolver.published[0][1]['is_pending'],0)

    def test_worker_cannot_initialize_app_classes(self):
        with self.assertRaisesRegex(RuntimeError,'entry thread'):
            self.run_worker(android_bridge.initialize)

    def test_failed_export_keeps_source_and_removes_pending_entry(self):
        android_bridge.initialize()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'song.m4a';path.write_bytes(b'audio')
            with patch.object(self.resolver,'openOutputStream',side_effect=OSError('no space')):
                with self.assertRaises(OSError):
                    self.run_worker(lambda:storage.publish(path,True))
            self.assertTrue(path.exists())
            self.assertEqual(self.resolver.deleted,['content://downloads/0'])

    def test_native_check_reads_back_and_removes_test_file(self):
        android_bridge.initialize()
        with tempfile.TemporaryDirectory() as d:
            storage.native_storage_check(d)
            self.assertEqual(list(Path(d).iterdir()),[])
        self.assertEqual(self.resolver.deleted,['content://downloads/0'])

    def test_clipboard_worker_uses_cached_activity(self):
        android_bridge.initialize()
        clip=SimpleNamespace(getItemCount=lambda:1,
            getItemAt=lambda _:SimpleNamespace(coerceToText=lambda _: 'https://www.jiosaavn.com/song/a/token'))
        self.clipboard.getPrimaryClip.return_value=clip
        self.assertEqual(self.run_worker(android_bridge.read_clipboard),'https://www.jiosaavn.com/song/a/token')


if __name__=='__main__':
    unittest.main()
