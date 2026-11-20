"""Launch JS-DL in its own Microsoft Edge application window."""
import ctypes
import os
import subprocess
import tempfile
import threading
from pathlib import Path

def run():
    data = Path(os.environ['LOCALAPPDATA']) / 'JS-DL'
    os.environ.setdefault('SAAVN_DATA_DIR', str(data))
    import main
    locations = [Path(os.environ.get(key, '')) / 'Microsoft/Edge/Application/msedge.exe'
                 for key in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')]
    edge = next((path for path in locations if path.is_file()), None)
    if not edge:
        raise RuntimeError('Install Microsoft Edge to open JS-DL.')
    with main.ThreadingHTTPServer(('127.0.0.1', 0), main.Handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}/'
        with tempfile.TemporaryDirectory(prefix='js-dl-window-', ignore_cleanup_errors=True) as profile:
            args = [str(edge), '--app='+url, '--user-data-dir='+profile,
                    '--no-first-run', '--no-default-browser-check', '--disable-background-mode',
                    '--window-size=1030,800']
            subprocess.run(args, check=True)
        # Allow an export started before closing the window to finish.
        while main.snapshot()['active']:
            threading.Event().wait(0.5)
        server.shutdown()

if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(None, str(exc), 'JS-DL 1.0', 0x10)
        raise SystemExit(1)
