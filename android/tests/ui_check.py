"""Browser checks against the actual local server with a deterministic service fixture."""
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from settings import Settings
from playwright.sync_api import sync_playwright, expect

SONGS = [
    {'id': 'one', 'song': 'A Song With a Very Long Title That Must Wrap on Small Screens',
     'album': 'Evening Sessions', 'primary_artists': 'Example Artist & Guest Singer',
     'duration':'241','year':'2024','language':'Hindi','perma_url':'https://www.jiosaavn.com/song/a/one'},
    {'id':'two', 'song':'<script>Not executable</script>', 'album':'Evening Sessions',
     'primary_artists':'Another Artist', 'duration':'185','year':'2024','language':'English',
     'perma_url':'https://www.jiosaavn.com/song/b/two'},
]
CALLS=[]


class FixtureClient:
    def search(self, query, page=1):
        return SONGS
    def search_albums(self,query,page=1):
        return [{'title':'Evening Sessions','artist':'Example Artist','year':'2024','image':'','matched_song':'A Song With a Very Long Title','url':'https://www.jiosaavn.com/album/evening/token'},
                {'title':'Other Album','artist':'Other Artist','year':'2023','image':'','url':'https://www.jiosaavn.com/album/other/token'}]
    def resolve(self, link):
        return {'kind':'playlist' if '/featured/' in link else 'album', 'title':'Evening Sessions','artist':'Example Artist',
                'year':'2024','image':'','songs':SONGS}
    def media_url(self, song, quality):
        CALLS.append(('play',quality))
        return 'https://aac.saavncdn.com/test.m4a'
    def download(self, song, directory, cancel, progress, settings, number, **kwargs):
        CALLS.append(('download',song['id'],settings['quality']))
        path=Path(directory)/(song['id']+'.m4a')
        path.write_bytes(b'test-fixture')
        progress(12,12)
        return path, []


def check():
    outputs=Path('ui-previews');outputs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as d, patch.object(main,'DATA',Path(d)), patch.object(main,'PREFS',Settings(Path(d)/'settings.json')), patch.object(main,'Client',FixtureClient):
        server=main.ThreadingHTTPServer(('127.0.0.1',5000),main.Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':393,'height':852},device_scale_factor=1)
                errors=[]
                page.on('pageerror',lambda e: errors.append(str(e)))
                for width,height in [(320,640),(360,800),(393,852),(768,1024),(740,360)]:
                    page.set_viewport_size({'width':width,'height':height})
                    page.goto('http://127.0.0.1:5000/')
                    expect(page.locator('#home-status')).to_have_text('Ready.')
                    expect(page.locator('#splash')).to_be_hidden(timeout=7000)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Home overflow at {width}'
                    assert page.locator('#archive').is_visible()
                    page.screenshot(path=str(outputs/f'home-{width}.png'),full_page=True)
                page.set_viewport_size({'width':393,'height':852})
                page.goto('http://127.0.0.1:5000/')
                expect(page.locator('#splash')).to_be_hidden(timeout=7000)
                page.get_by_role('button',name='Open settings').first.click()
                expect(page.locator('#settings')).to_be_visible()
                page.screenshot(path=str(outputs/'settings-393.png'),full_page=True)
                page.get_by_text('Region, audio format and quality',exact=True).click()
                page.locator('#quality').select_option('160')
                expect(page.locator('#settings-status')).to_have_text('Changes save automatically.')
                assert main.PREFS.get()['quality']=='160'
                page.get_by_text('Names, disc folders and ZIP layout',exact=True).click()
                template=page.locator('[data-setting="single_track_template"]')
                template.fill('{artist} - {title}')
                template.press('Tab')
                expect(page.locator('[data-preview="single_track_template"]')).to_have_text('Artist - Track title.m4a')
                expect(page.locator('#settings-status')).to_have_text('Changes save automatically.')
                assert main.PREFS.get()['single_track_template']=='{artist} - {title}'
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(outputs/'filenames-393.png'),full_page=True)
                page.reload()
                expect(page.locator('#splash')).to_be_hidden(timeout=7000)
                expect(page.locator('#quality')).to_have_value('160')
                expect(page.locator('[data-setting="single_track_template"]')).to_have_value('{artist} - {title}')
                page.locator('#settings-back').click()
                page.locator('#query').fill('https://www.jiosaavn.com/album/evening/token')
                page.locator('#archive').click()
                expect(page.locator('#details')).to_be_visible()
                expect(page.locator('#tracks .track')).to_have_count(2)
                assert not any(call[0]=='download' for call in CALLS), 'Archive unexpectedly downloaded a song'
                expect(page.locator('#tracks h3').nth(1)).to_have_text('<script>Not executable</script>')
                for width in [320,393,768]:
                    page.set_viewport_size({'width':width,'height':852})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Details overflow at {width}'
                page.set_viewport_size({'width':393,'height':852})
                page.screenshot(path=str(outputs/'album-393.png'),full_page=True)
                # Browser media fixture permits real play() without external CDN access.
                import io, wave
                buf=io.BytesIO()
                with wave.open(buf,'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000)
                    wav.writeframes(bytes(8000*2*30))
                page.route('https://aac.saavncdn.com/test.m4a',lambda route:route.fulfill(status=200,content_type='audio/wav',body=buf.getvalue()))
                expect(page.locator('#home footer')).to_contain_text('Original source and credit to Bunnykek')
                expect(page.locator('#home footer')).to_contain_text('App by James')
                assert page.locator('footer a').count()==0
                for link,heading in [('https://www.jiosaavn.com/featured/example/token','Playlist details'),('https://www.jiosaavn.com/album/evening/token','Album details')]:
                    page.locator('#details-back').click()
                    page.locator('#query').fill(link);page.locator('#archive').click()
                    expect(page.locator('#details-heading')).to_have_text(heading)
                    page.locator('#play-all').click()
                    expect(page.locator('#queue-position')).to_have_text('1 / 2')
                    page.wait_for_function("!document.getElementById('audio').paused")
                    page.evaluate("document.getElementById('audio').dispatchEvent(new Event('ended'))")
                    expect(page.locator('#queue-position')).to_have_text('2 / 2')
                    expect(page.locator('#player-title')).to_have_text('<script>Not executable</script>')
                    page.wait_for_function("!document.getElementById('audio').paused")
                    page.evaluate("document.getElementById('audio').dispatchEvent(new Event('ended'))")
                    expect(page.locator('#player-status')).to_have_text('Playback finished.')
                    page.locator('#player-repeat').select_option('all')
                    page.evaluate("document.getElementById('audio').dispatchEvent(new Event('ended'))")
                    expect(page.locator('#queue-position')).to_have_text('1 / 2')
                    page.wait_for_function("!document.getElementById('audio').paused")
                    page.locator('#player-repeat').select_option('one')
                    assert page.locator('#audio').evaluate('(a)=>a.loop')
                    title=page.locator('#player-title').inner_text()
                    page.evaluate("document.getElementById('audio').dispatchEvent(new Event('ended'))")
                    expect(page.locator('#player-title')).to_have_text(title)
                    expect(page.locator('#queue-position')).to_have_text('1 / 2')
                    page.locator('#player-next').click()
                    expect(page.locator('#queue-position')).to_have_text('2 / 2')
                    page.locator('#player-repeat').select_option('off')
                    assert not page.locator('#audio').evaluate('(a)=>a.loop')
                    page.locator('#player-previous').click()
                    expect(page.locator('#queue-position')).to_have_text('1 / 2')
                    page.locator('#shuffle-all').click()
                    expect(page.locator('#player-shuffle')).to_have_attribute('aria-pressed','true')
                    assert page.evaluate('new Set(playbackQueue.map(s=>s.key)).size===2')
                    page.locator('#close-player').click()
                    expect(page.locator('#player')).to_be_hidden()
                page.locator('.track-check').nth(1).uncheck()
                expect(page.locator('#download-selected')).to_have_text('Download selected (1)')
                page.locator('#download-selected').click()
                expect(page.locator('#job-message')).to_have_text('Saved 1 song.',timeout=10000)
                downloads=[call for call in CALLS if call[0]=='download']
                assert downloads==[('download','one','160')], downloads
                page.locator('#details-back').click()
                page.locator('#query').fill('Artist name')
                page.locator('#archive').click()
                expect(page.locator('#details-heading')).to_have_text('Search results')
                expect(page.locator('#tracks .track')).to_have_count(2)
                page.locator('#result-modes [data-search-type="albums"]').click()
                expect(page.locator('#details-heading')).to_have_text('Album results')
                expect(page.locator('#albums .album-card')).to_have_count(2)
                expect(page.locator('#tracks')).to_be_hidden()
                for width,height in [(320,640),(393,852),(740,360)]:
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'Album results overflow at {width}'
                page.set_viewport_size({'width':393,'height':852})
                page.wait_for_timeout(300)
                page.screenshot(path=str(outputs/'album-search-393.png'),full_page=True)
                page.get_by_role('button',name='Open album Evening Sessions',exact=True).click()
                expect(page.locator('#details-heading')).to_have_text('Album details')
                expect(page.locator('#tracks .track')).to_have_count(2)
                expect(page.locator('#albums')).to_be_hidden()
                expect(page.locator('#collection')).to_contain_text('Evening Sessions')
                expect(page.locator('#collection')).not_to_contain_text('Other Album')
                main.PREFS.save({'zip_album':False})
                page.locator('#select-none').click()
                page.locator('#download-album-zip').click()
                expect(page.locator('#job-message')).to_have_text('Saved 2 songs.',timeout=10000)
                archives=list(Path(d).rglob('*.zip'))
                assert len(archives)==1,archives
                with main.zipfile.ZipFile(archives[0]) as archive:
                    assert sorted(Path(n).name for n in archive.namelist())==['one.m4a','two.m4a']
                page.wait_for_timeout(300)
                page.screenshot(path=str(outputs/'album-zip-393.png'),full_page=True)
                page.locator('#details-back').click()
                expect(page.locator('#details-heading')).to_have_text('Album results')
                expect(page.locator('#albums .album-card')).to_have_count(2)
                assert not errors, errors
                # On Android the persistent native overlay is already playing;
                # the app page must not paint or restart another CSS splash.
                native=browser.new_page(viewport={'width':393,'height':852})
                handoffs=[]
                native.on('request',lambda request: handoffs.append(request.url) if request.url.endswith('/api/startup/ready') else None)
                native.add_init_script("window.splashAnimations=0;document.addEventListener('animationstart',event=>{if(event.target.closest('#splash'))window.splashAnimations++;},true);")
                android_html=(main.ROOT/'web/index.html').read_text().replace('__APP_TOKEN__',main.TOKEN).replace('<html lang="en">','<html lang="en" class="native-startup">')
                native.route('http://127.0.0.1:5000/',lambda route:route.fulfill(status=200,content_type='text/html',body=android_html))
                with native.expect_request('**/api/startup/ready'):
                    native.goto('http://127.0.0.1:5000/')
                expect(native.locator('#splash')).to_be_hidden()
                native.wait_for_function('document.querySelector("#home-status").textContent === "Ready."')
                native.wait_for_timeout(700)
                assert len(handoffs)==1,handoffs
                assert native.evaluate('window.splashAnimations')==0,'App page replayed the startup animation'
                native.close()
                browser.close()
        finally:
            server.shutdown();server.server_close()
    print('PASS: 5 home sizes, 3 details sizes, settings persistence, preview-first flow, selected download, quality wiring, safe text rendering, search, no JS errors.')


if __name__=='__main__':
    check()
