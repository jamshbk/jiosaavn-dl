"""Windows output directory and native folder selection."""
import os
import threading
import winreg
from pathlib import Path

lock = threading.RLock()
pending = False
picker_error = ''

def selection_file():
    return Path(os.environ['SAAVN_DATA_DIR']) / 'destination.txt'

def custom_folder():
    try:
        return selection_file().read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        return ''

def downloads_folder():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
            value, _ = winreg.QueryValueEx(key, '{374DE290-123F-4565-9164-39C4925E467B}')
            return Path(os.path.expandvars(value))
    except OSError:
        return Path.home() / 'Downloads'

def output_folder(name):
    custom = custom_folder()
    return Path(custom) if custom else downloads_folder() / name

def destination_state(name):
    with lock:
        return dict(uri=custom_folder(), path=str(output_folder(name)), pending=pending,
                    error=picker_error, desktop=True)

def pick_folder():
    import tkinter as tk
    from tkinter import filedialog
    global pending, picker_error
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        chosen = filedialog.askdirectory(parent=root, title='Choose your download folder',
                                         initialdir=custom_folder() or str(downloads_folder()))
        if chosen:
            target = selection_file()
            temp = target.with_suffix('.tmp')
            temp.write_text(chosen, encoding='utf-8')
            temp.replace(target)
    except Exception as exc:
        picker_error = str(exc)
    finally:
        if root is not None:
            root.destroy()
        with lock:
            pending = False

def change_destination(pick, name):
    global pending, picker_error
    with lock:
        if not pending:
            picker_error = ''
            if pick:
                pending = True
                threading.Thread(target=pick_folder, daemon=True).start()
            else:
                selection_file().unlink(missing_ok=True)
        return destination_state(name)
