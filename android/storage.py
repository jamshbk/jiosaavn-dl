"""Publish completed audio to shared Downloads on Android 10+."""
from pathlib import Path
from android_bridge import get_bridge


def publish(path, android=False, folder='JS-DL', subfolder=''):
    if not android:
        return str(path)
    destination=get_destination()
    if destination.get('uri'):
        suffix=Path(path).suffix.lower()
        mime={'.m4a':'audio/mp4','.zip':'application/zip','.txt':'text/plain'}.get(suffix,'application/octet-stream')
        name=get_bridge()['NativeUi'].exportToFolder(str(path),subfolder,mime)
        Path(path).unlink()
        return destination.get('path',destination['label'])+'/'+(subfolder+'/' if subfolder else '')+str(name)
    destination, uri = _publish_file(path, folder, subfolder)
    return destination


def get_destination():
    import json
    return json.loads(str(get_bridge()['NativeUi'].getDestination()))


def choose_destination():
    get_bridge()['NativeUi'].chooseFolder()
    return get_destination()


def reset_destination():
    get_bridge()['NativeUi'].useDefaultFolder()
    return get_destination()


def _publish_file(path, folder, subfolder):
    cached = get_bridge()
    Values, Downloads, Integer = (cached[k] for k in ('Values', 'Downloads', 'Integer'))
    FileInputStream, Channels = (cached[k] for k in ('FileInputStream', 'Channels'))
    resolver = cached['resolver']
    values = Values()
    values.put('_display_name', Path(path).name)
    suffix = Path(path).suffix.lower()
    values.put('mime_type', {'.m4a': 'audio/mp4', '.zip': 'application/zip', '.txt': 'text/plain'}.get(suffix, 'application/octet-stream'))
    relative = 'Download/' + folder.strip('/') + '/' + (subfolder.strip('/') + '/' if subfolder else '')
    values.put('relative_path', relative)
    values.put('is_pending', Integer(1))
    uri = resolver.insert(Downloads.EXTERNAL_CONTENT_URI, values)
    if uri is None:
        raise OSError('Could not create a file in Downloads.')
    source = output = None
    try:
        output = resolver.openOutputStream(uri)
        if output is None:
            raise OSError('Could not open the Downloads file.')
        source = FileInputStream(str(path))
        channel = source.getChannel()
        destination = Channels.newChannel(output)
        position, size = 0, channel.size()
        while position < size:
            transferred = channel.transferTo(position, size - position, destination)
            if transferred <= 0:
                raise OSError('Could not finish saving the download.')
            position += transferred
        output.close()
        output = None
        source.close()
        source = None
        values.clear()
        values.put('is_pending', Integer(0))
        resolver.update(uri, values, None, None)
    except Exception:
        resolver.delete(uri, None, None)
        raise
    finally:
        if source is not None:
            source.close()
        if output is not None:
            output.close()
    Path(path).unlink()
    return relative + Path(path).name, uri


def native_storage_check(directory):
    """CI-only intent check: export on a worker, read back, then remove the file."""
    import threading
    import secrets
    result = []
    def worker():
        resolver = get_bridge()['resolver']
        path = Path(directory) / ('native-check-' + secrets.token_hex(8) + '.txt')
        payload = b'Saavn Pocket Android storage worker check\n'
        uri = None
        stream = None
        try:
            path.write_bytes(payload)
            _, uri = _publish_file(path, 'SaavnPocket', '')
            stream = resolver.openInputStream(uri)
            if stream is None:
                raise RuntimeError('Published file cannot be read back.')
            received = bytearray()
            while True:
                byte = stream.read()
                if byte == -1:
                    break
                received.append(byte)
            if bytes(received) != payload:
                raise RuntimeError('Published file content did not match.')
            result.append(None)
        except Exception as error:
            result.append(error)
        finally:
            if stream is not None:
                stream.close()
            if uri is not None:
                resolver.delete(uri, None, None)
            path.unlink(missing_ok=True)
    thread = threading.Thread(target=worker, name='NativeStorageCheck')
    thread.start()
    thread.join(30)
    if thread.is_alive():
        raise RuntimeError('Android storage check timed out.')
    if not result or result[0] is not None:
        raise RuntimeError('Android storage worker check failed: ' + str(result[0] if result else 'no result'))

