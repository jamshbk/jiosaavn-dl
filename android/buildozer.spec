[app]
title = Saavn Pocket
package.name = saavnpocket
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,json,ttf,html,css,js
source.exclude_dirs = tests,.git,.github,__pycache__,bin,.buildozer,Downloads,appdata,ui-previews
version = 0.2.0
requirements = python3,requests,certifi,charset_normalizer,idna,urllib3,mutagen,pyjnius
orientation = portrait, landscape
fullscreen = 0
android.permissions = INTERNET
android.api = 35
android.minapi = 29
android.archs = arm64-v8a
android.accept_sdk_license = True
android.debug_artifact = apk
android.numeric_version = 200
p4a.bootstrap = webview
[buildozer]
log_level = 2
warn_on_root = 1
