"""Safe user-editable names. Templates produce one filename, never a path."""
import html
import re
from string import Formatter

FIELDS = {'title','artist','albumArtist','album','year','track','disc','id','language'}
TEMPLATE_KEYS = ('single_track_template','album_zip_template','album_track_template','multidisc_track_template')


def validate_template(value):
    if not isinstance(value,str) or not value.strip() or len(value)>180:
        raise ValueError('Filename templates must contain 1–180 characters.')
    if any(c in value for c in '/\\') or any(ord(c)<32 for c in value):
        raise ValueError('Folder separators and control characters are not allowed in filenames.')
    try:
        for _,field,spec,conversion in Formatter().parse(value):
            if field is not None and (field not in FIELDS or spec or conversion):
                raise ValueError('Use only the available filename placeholders, without format modifiers.')
    except ValueError as error:
        raise ValueError(str(error))
    return value.strip()


def clean_name(value):
    value=html.unescape(str(value or ''))
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',value).strip(' .')
    return value.encode('utf-8')[:180].decode('utf-8','ignore') or 'Untitled'


def render_name(template,song,number=1,album_artist=None,album_name=None):
    validate_template(template)
    values={
        'title':html.unescape(str(song.get('song') or song.get('title') or 'Untitled')),
        'artist':html.unescape(str(song.get('primary_artists') or 'Unknown artist')),
        'albumArtist':html.unescape(str(album_artist or song.get('album_artist') or song.get('primary_artists') or 'Unknown artist')),
        'album':html.unescape(str(album_name or song.get('album') or 'Unknown album')),
        'year':str(song.get('year') or 'Unknown year'),
        'track':str(number).zfill(2), 'disc':str(song.get('disc_number') or 1),
        'id':str(song.get('id') or ''), 'language':str(song.get('language') or ''),
    }
    name=clean_name(template.format_map(values))
    for extension in ('.m4a','.aac','.zip'):
        if name.lower().endswith(extension):
            name=name[:-len(extension)].rstrip(' .') or 'Untitled'
            break
    return name


def track_name(song,settings,number=1,context='single',album_artist=None):
    key='single_track_template' if context=='single' else 'multidisc_track_template' if context=='multidisc' else 'album_track_template'
    return render_name(settings[key],song,number,album_artist)
