[app]
title = Saavn Pocket
package.name = saavnpocket
package.domain = org.example
source.dir = .
source.include_exts = py,kv,png,jpg,json,ttf
source.exclude_dirs = tests,.git,.github,__pycache__,bin,.buildozer,Downloads
version = 0.1.0
requirements = python3,kivy,requests,certifi,charset_normalizer,idna,urllib3,mutagen,pyjnius
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.api = 35
android.minapi = 29
android.archs = arm64-v8a
android.accept_sdk_license = True
android.debug_artifact = apk
[buildozer]
log_level = 2
warn_on_root = 1
