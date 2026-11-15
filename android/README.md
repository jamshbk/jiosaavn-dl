# Saavn Pocket 0.2.0

Python Android application with a responsive local WebView UI. The Python server
binds only to 127.0.0.1. No external server or user account is needed by the app.

## Changes

- Screenshot-inspired dark home screen, gradient, Archive bar and settings.
- Responsive phone, landscape and tablet layout; system font supports Unicode.
- Archive previews song/album/playlist information before any download.
- Track selection, individual downloads, album ZIP and optional folder layout.
- Playback with native audio controls and 96/160/320 kbps quality requests.
- Saved preferences: names, folders, cover art, date/explicit tags and lyrics.
- Progress, cancellation and visible per-song errors.

M4A/AAC is the supported format. Region follows the current connection; this app
does not offer a region override. Requested bitrate depends on service availability.
Keep the app open for playback and downloads; no foreground service is included.

## Desktop preview

```sh
python -m pip install requests mutagen
python main.py
```

Open http://127.0.0.1:5000. Desktop downloads and preferences go in appdata/.
Android exports completed files to the selected folder under shared Downloads.

## Checks

```sh
python -m unittest discover -s tests -v
python -m pip install playwright
python -m playwright install --with-deps chromium
python tests/ui_check.py
```

Browser checks use deterministic service fixtures and cover responsive layouts,
settings persistence, the preview-first flow, safe rendering and selected downloads.
They do not establish live-service compatibility or Android playback/storage behavior.

## APK

The GitHub workflow builds Android 10+ ARM64 debug APKs and publishes a release
asset for direct download. The 0.2.0 build uses a new debug signing identity.
Uninstall 0.1.0 if Android rejects an update with a signature conflict. Subsequent
0.2.x builds cache the debug signing identity. Physical-phone testing is still needed.

Upstream reference: https://github.com/bunnykek/jiosaavn-dl
