import threading
from pathlib import Path
from functools import partial
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform
from backend import Client, Cancelled, clean
from storage import publish

ACCENT = (.12, .72, .58, 1)


def button(text, callback, **kwargs):
    widget = Button(text=text, background_normal='', background_color=ACCENT,
                    color=(.03, .08, .10, 1), **kwargs)
    widget.bind(on_release=callback)
    return widget


class SaavnPocket(App):
    title = 'Saavn Pocket'

    def build(self):
        Window.clearcolor = (.04, .06, .10, 1)
        self.busy = False
        self.cancel_event = threading.Event()
        self.query = ''
        self.page = 1
        self.controls = []
        root = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(10))
        root.add_widget(Label(text='SAAVN POCKET', font_size='25sp', bold=True,
                              size_hint_y=None, height=dp(44)))
        root.add_widget(Label(text='Search a song. Save a favourite.', color=(.65, .74, .8, 1),
                              size_hint_y=None, height=dp(26)))
        self.input = TextInput(hint_text='Song / artist name or JioSaavn link', multiline=False,
                               font_size='16sp', size_hint_y=None, height=dp(50), padding=dp(12))
        self.input.bind(on_text_validate=self.search)
        root.add_widget(self.input)
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.controls = [button('Search', self.search), button('Download link', self.from_link)]
        for control in self.controls:
            actions.add_widget(control)
        root.add_widget(actions)
        scroll = ScrollView()
        self.results = BoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None)
        self.results.bind(minimum_height=self.results.setter('height'))
        scroll.add_widget(self.results)
        root.add_widget(scroll)
        self.bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(10))
        root.add_widget(self.bar)
        self.status = Label(text='Search to get started.', font_size='13sp',
                            size_hint_y=None, height=dp(70), halign='left', valign='middle')
        self.status.bind(size=lambda w, size: setattr(w, 'text_size', size))
        root.add_widget(self.status)
        self.cancel_button = button('Cancel download', lambda *_: self.cancel_event.set(),
                                     size_hint_y=None, height=dp(40), disabled=True)
        root.add_widget(self.cancel_button)
        self.results.add_widget(Label(text='Your next favourite is a search away.',
                                      size_hint_y=None, height=dp(100)))
        return root

    def ui(self, callback, *args):
        Clock.schedule_once(lambda dt: callback(*args), 0)

    def message(self, text):
        self.ui(setattr, self.status, 'text', text)

    def set_busy(self, value, downloading=False):
        self.busy = value
        self.input.disabled = value
        for control in self.controls:
            control.disabled = value
        self.cancel_button.disabled = not (value and downloading)

    def run_job(self, job, downloading=False):
        if self.busy:
            return
        self.set_busy(True, downloading)
        self.cancel_event.clear()
        self.bar.value = 0
        def worker():
            try:
                job()
            except Cancelled:
                self.message('Cancelled. Completed songs are kept.')
            except Exception as error:
                self.message('Could not finish: ' + str(error)[:220])
            finally:
                self.ui(self.set_busy, False)
        threading.Thread(target=worker, daemon=True).start()

    def search(self, *_):
        query = self.input.text.strip()
        if not query:
            self.message('Enter a song or artist name.')
            return
        if query.startswith('https://'):
            self.from_link()
            return
        self.query, self.page = query, 1
        self.fetch_page()

    def fetch_page(self):
        query, page = self.query, self.page
        def job():
            self.message('Searching...')
            songs = Client().search(query, page)
            self.ui(self.show_results, songs)
            self.message(f'{len(songs)} results - page {page}' if songs else 'No songs found. Try another name.')
        self.run_job(job)

    def show_results(self, songs):
        self.results.clear_widgets()
        for song in songs:
            row = BoxLayout(size_hint_y=None, height=dp(104), spacing=dp(10), padding=dp(4))
            row.add_widget(AsyncImage(source=song.get('image') or '', size_hint_x=None, width=dp(70)))
            info = BoxLayout(orientation='vertical')
            for text, size in [(clean(song.get('song')), '16sp'),
                               (clean(song.get('primary_artists')), '12sp')]:
                label = Label(text=text, font_size=size, halign='left', valign='middle', shorten=True,
                              shorten_from='right')
                label.bind(size=lambda w, value: setattr(w, 'text_size', value))
                info.add_widget(label)
            row.add_widget(info)
            row.add_widget(button('Download', partial(self.download_song, song),
                                  size_hint_x=None, width=dp(88)))
            self.results.add_widget(row)
        pages = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        pages.add_widget(button('Previous', lambda *_: self.change_page(-1), disabled=self.page <= 1))
        pages.add_widget(button('Next', lambda *_: self.change_page(1), disabled=len(songs) < 20))
        self.results.add_widget(pages)

    def change_page(self, delta):
        if not self.busy:
            self.page = max(1, self.page + delta)
            self.fetch_page()

    def from_link(self, *_):
        link = self.input.text.strip()
        def job():
            self.message('Reading link...')
            client = Client()
            self.download_many(client, client.resolve(link))
        self.run_job(job, downloading=True)

    def download_song(self, song, *_):
        self.run_job(lambda: self.download_many(Client(), [song]), downloading=True)

    def download_many(self, client, songs):
        android = platform == 'android'
        directory = Path(self.user_data_dir) / 'staging' if android else Path.cwd() / 'Downloads'
        directory.mkdir(parents=True, exist_ok=True)
        succeeded, failed, warnings = 0, 0, 0
        for index, song in enumerate(songs, 1):
            if self.cancel_event.is_set():
                raise Cancelled()
            name = clean(song.get('song'))
            last_update = [0]
            def progress(done, total):
                # Keep the UI queue small during fast downloads.
                if done - last_update[0] < 256 * 1024 and done != total:
                    return
                last_update[0] = done
                percent = done / total * 100 if total else 0
                self.ui(setattr, self.bar, 'value', percent)
                self.message(f'{index}/{len(songs)}: {name}\n' +
                             (f'{percent:.0f}%' if total else f'{done / 1048576:.1f} MB'))
            try:
                path, notes = client.download(song, directory, self.cancel_event, progress)
                publish(path, android)
                succeeded += 1
                warnings += len(notes)
            except Cancelled:
                raise
            except Exception as error:
                failed += 1
                self.message(f'{name}: {error}')
                if len(songs) == 1:
                    raise
        self.ui(setattr, self.bar, 'value', 100 if succeeded else 0)
        location = 'Downloads/SaavnPocket' if android else str(directory)
        self.message(f'Saved {succeeded}; failed {failed}; metadata warnings {warnings}.\n{location}')

    def on_stop(self):
        self.cancel_event.set()


if __name__ == '__main__':
    SaavnPocket().run()
