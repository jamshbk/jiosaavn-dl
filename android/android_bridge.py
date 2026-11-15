"""Cache app Java references on the Java-created Python entry thread.

JNI FindClass on a Python-created worker uses Android's boot class loader and
cannot resolve application classes. Never discover PythonActivity in a worker.
"""
import threading

_bridge = None
_error = ''
_lock = threading.Lock()


def initialize():
    global _bridge, _error
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Android bridge must initialize on the Python entry thread.')
    with _lock:
        if _bridge is not None:
            return _bridge
        try:
            from jnius import autoclass
            activity_class = autoclass('org.kivy.android.PythonActivity')
            activity = activity_class.mActivity
            if activity is None:
                raise RuntimeError('Android activity is not ready.')
            classes = {
                'Values': 'android.content.ContentValues',
                'Downloads': 'android.provider.MediaStore$Downloads',
                'Integer': 'java.lang.Integer',
                'FileInputStream': 'java.io.FileInputStream',
                'Channels': 'java.nio.channels.Channels',
            }
            cached = {key: autoclass(name) for key, name in classes.items()}
            cached.update(activity=activity, resolver=activity.getContentResolver(),
                          clipboard=activity.getSystemService('clipboard'))
            _bridge = cached
            _error = ''
            return _bridge
        except Exception as error:
            _error = str(error)
            raise


def get_bridge():
    if _bridge is None:
        raise RuntimeError('Android storage is not ready. Close and reopen the app. ' + _error)
    return _bridge


def read_clipboard():
    cached = get_bridge()
    clip = cached['clipboard'].getPrimaryClip()
    if clip is None or not clip.getItemCount():
        return ''
    value = clip.getItemAt(0).coerceToText(cached['activity'])
    return str(value.toString() if hasattr(value, 'toString') else value)
