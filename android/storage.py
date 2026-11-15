"""Publish completed audio to shared Downloads on Android 10+."""
from pathlib import Path


def publish(path, android=False):
    if not android:
        return str(path)
    from jnius import autoclass
    Activity = autoclass('org.kivy.android.PythonActivity')
    Values = autoclass('android.content.ContentValues')
    Downloads = autoclass('android.provider.MediaStore$Downloads')
    Integer = autoclass('java.lang.Integer')
    FileInputStream = autoclass('java.io.FileInputStream')
    Channels = autoclass('java.nio.channels.Channels')
    resolver = Activity.mActivity.getContentResolver()
    values = Values()
    values.put('_display_name', Path(path).name)
    values.put('mime_type', 'audio/mp4')
    values.put('relative_path', 'Download/SaavnPocket/')
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
    return 'Downloads/SaavnPocket/' + Path(path).name
