"""Validated, atomic application preferences."""
import json
import threading
from pathlib import Path
from filenames import TEMPLATE_KEYS, validate_template

DEFAULTS = {
    'quality': '320', 'folder': 'JS-DL', 'naming': 'title_artist',
    'single_track_template': '{title}',
    'album_zip_template': '{albumArtist} - {album} ({year})',
    'album_track_template': '{title}',
    'multidisc_track_template': '{disc}-{track}. {title}',
    'album_folders': True, 'disc_folders': False, 'zip_album': False,
    'explicit_tag': True, 'original_date': True, 'embed_lyrics': True,
    'save_lyrics': False, 'cover_art': True,
}


def validate(values):
    if not isinstance(values, dict):
        raise ValueError('Settings must be an object.')
    result = dict(DEFAULTS)
    for key in DEFAULTS:
        if key not in values:
            continue
        value = values[key]
        if isinstance(DEFAULTS[key], bool):
            if not isinstance(value, bool):
                raise ValueError('Invalid setting: ' + key)
        elif not isinstance(value, str):
            raise ValueError('Invalid setting: ' + key)
        result[key] = value
    if result['quality'] not in ('96', '160', '320'):
        raise ValueError('Choose 96, 160 or 320 kbps.')
    if result['naming'] not in ('title_artist', 'title', 'track_title'):
        raise ValueError('Invalid file naming option.')
    for key in TEMPLATE_KEYS:
        result[key]=validate_template(result[key])
    folder = result['folder'].strip()
    if not folder or len(folder) > 60 or any(c in folder for c in '/\\<>:"|?*') or folder in ('.', '..') or any(ord(c) < 32 for c in folder):
        raise ValueError('Folder name must be 1–60 characters without path separators.')
    result['folder'] = folder
    return result


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        try:
            saved=json.loads(self.path.read_text(encoding='utf-8'))
            if saved.get('folder') in ('SaavnPocket','SaavnDl'):saved['folder']='JS-DL'
            if 'single_track_template' not in saved and 'naming' in saved:
                saved['single_track_template']={'title_artist':'{title} - {artist}','title':'{title}','track_title':'{track}. {title}'}.get(saved['naming'],'{title}')
            self.values = validate(saved)
        except (OSError, ValueError):
            self.values = dict(DEFAULTS)

    def get(self):
        with self.lock:
            return dict(self.values)

    def save(self, patch=None, reset=False):
        with self.lock:
            values = validate(DEFAULTS if reset else {**self.values, **(patch or {})})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.path)
            self.values = values
            return dict(values)
