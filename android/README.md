# SaavnDl 1.0

Android 10+ ARM64 music app, with a local-only Python server and responsive WebView UI.

## Version 1.0

- Native status/navigation/cutout insets in portrait and landscape.
- Four validated filename templates with live previews; Unicode-safe names.
- Persistent Android folder picker for custom phone or SD-card destinations.
- Original SaavnDl launcher logo and animated splash; reduced-motion support.
- Smooth page/button/accordion transitions.
- Song/album previews, selected downloads, quality controls and optional album ZIP.

The Android picker controls which folders can be granted. Restricted root folders
cannot be bypassed. Files saved to a chosen folder use that folder directly;
album/disc subfolders follow the selected preferences. The Downloads subfolder
setting applies only to the default MediaStore destination.

Filename placeholders: `{title}`, `{artist}`, `{albumArtist}`, `{album}`, `{year}`,
`{track}`, `{disc}`, `{id}`, `{language}`. File extensions are appended automatically.
When disc metadata is unavailable, tracks are treated as Disc 1. M4A/AAC is the
supported audio format. Quality is requested from the service and depends on availability.

The package ID remains org.example.saavnpocket so signed-compatible builds can
update an existing installation. The visible app name is SaavnDl and version 1.0.

## Checks

Run `python -m unittest discover -s tests -v` from android/ for logic and bridge tests.
`python tests/ui_check.py` checks responsive screens with deterministic fixtures.
The CI pipeline builds phone and emulator APKs separately, then checks native
storage, system-bar insets and persisted custom-folder access on Android emulators.
These checks do not replace testing the user's physical phone or the live service.

Desktop preview: install requirements.txt, run `python main.py`, then open
http://127.0.0.1:5000. Native folder selection is available in the Android app.

Upstream reference: https://github.com/bunnykek/jiosaavn-dl
