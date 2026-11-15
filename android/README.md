# Saavn Pocket — Android Python prototype

Search by song/artist name, browse 20 results per page, download a selected
song or paste a JioSaavn song/album/playlist link. Includes cover art, basic
tags, optional lyrics, byte progress, cancellation and per-track failure counts.
Songs are M4A/AAC, not MP3. Android target: Android 10+, ARM64 phones.

## Current status

Source prototype; no APK has been built or tested on a phone. The live search
endpoint returned song results during inspection. The Python client, actual
downloads, packaging and Android MediaStore integration still require end-to-end
testing. JioSaavn uses unofficial endpoints here and can change their response
format or availability. Files are exported to Downloads/SaavnPocket after tagging.
Search is song search; artist names can be used as queries. It does not browse
artist profiles or search albums/playlists as separate result categories.

Downloads run on a worker thread while the app is open. This version does not
provide an Android foreground service: keep the app open during downloads.
There is no playback, resumable transfer or duplicate-download history yet.
Large playlists are rejected if the service returns only a partial track list,
so the app does not silently report a partial playlist as complete.
An export failure retains the staged audio inside app data for recovery.
Use only for content you are permitted to download.

## APK banana (GitHub se)

1. ZIP extract karein. `main.py`, `backend.py`, `storage.py`, `buildozer.spec`
   aur `.github` folder ko apne GitHub repo ke root mein rakhein.
2. GitHub mein Actions → Build Android APK → Run workflow karein.
3. Build successful hone par `saavn-pocket-debug-apk` artifact download karein.
4. Artifact ZIP ke andar APK hoga; apne Android 10+ ARM64 phone par install karein.

The workflow builds a debug APK, not a Play Store release. Its first run downloads
the Android toolchain and can take a while. Build dependencies may need changes
if python-for-android or the Android SDK changes. No repository was created,
uploaded or modified on your account by this task.

## Desktop preview

With Python 3.11 installed:

```sh
python -m pip install -r requirements.txt
python main.py
```

Desktop audio is saved to the project's Downloads directory.

## Linux / WSL build

Use Ubuntu 22.04, Python 3.11, JDK 17, and the dependencies from
`.github/workflows/android.yml`. Keep the project in the Linux filesystem.

```sh
python -m pip install buildozer==1.5.0 Cython==0.29.36 setuptools
buildozer -v android debug
```

## Checks before calling this ready

- Search with a Hindi/English song title and artist name; test empty/no results.
- Download one permitted track and verify playback, tags and its Downloads entry.
- Paste an album and playlist link; check counts and failures.
- Cancel a transfer; interrupt Wi-Fi; confirm no partial audio is exported.
- Verify on a physical Android 10+ device and a current Android version.

References: https://kivy.org/doc/stable/guide/android.html and
https://developer.android.com/training/data-storage/shared/media
