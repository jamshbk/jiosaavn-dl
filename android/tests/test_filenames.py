import unittest
from filenames import render_name, track_name, validate_template
from settings import DEFAULTS, validate
import main

SONG={'song':'A / New Song','primary_artists':'An Artist','album':'Album','year':'2026','id':'abc','disc_number':'2'}


class FilenameTests(unittest.TestCase):
    def test_user_templates_and_auto_extensions(self):
        self.assertEqual(render_name('{artist} - {title}',SONG),'An Artist - A _ New Song')
        self.assertEqual(render_name('{albumArtist} - {album} ({year}).zip',SONG,album_artist='Various Artists'),'Various Artists - Album (2026)')
        self.assertEqual(render_name('{disc}-{track}. {title}',SONG,3),'2-03. A _ New Song')

    def test_invalid_templates_are_rejected(self):
        for template in ('', '../{title}', '{artist}/{title}', '{title.__class__}', '{missing}', '{track:02d}', '{title!r}', '{title'):
            with self.subTest(template=template),self.assertRaises(ValueError):
                validate_template(template)

    def test_unicode_filename_stays_within_byte_limit(self):
        result=render_name('{title}',{'song':'संगीत'*100})
        self.assertLessEqual(len(result.encode('utf-8')),180)
        self.assertTrue(result)

    def test_context_chooses_correct_template(self):
        options={**DEFAULTS,'single_track_template':'Single {title}','album_track_template':'{track} {title}','multidisc_track_template':'{disc}-{track} {title}'}
        self.assertEqual(track_name(SONG,options,3),'Single A _ New Song')
        self.assertEqual(track_name(SONG,options,3,'album'),'03 A _ New Song')
        self.assertEqual(track_name(SONG,options,3,'multidisc'),'2-03 A _ New Song')

    def test_multidisc_uses_local_track_numbers(self):
        songs=[{**SONG,'disc_number':'1'},{**SONG,'disc_number':'1'},{**SONG,'disc_number':'2'}]
        items=main.register(songs,'Album','album','Album Artist')
        records=[main.CATALOG[item['key']] for item in items]
        self.assertEqual([r['number'] for r in records],[1,2,1])
        self.assertTrue(all(r['context']=='multidisc' for r in records))

    def test_templates_are_validated_as_preferences(self):
        options=validate({'single_track_template':'{title} - {year}'})
        self.assertEqual(options['single_track_template'],'{title} - {year}')
        with self.assertRaises(ValueError):validate({'album_zip_template':'../../secret'})


if __name__=='__main__':unittest.main()
