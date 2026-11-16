[app]
title = SaavnDl
package.name = saavnpocket
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,json,ttf,html,css,js
source.exclude_dirs = tests,.git,.github,__pycache__,bin,.buildozer,Downloads,appdata,ui-previews
version = 1.0
requirements = python3,requests,certifi,charset_normalizer,idna,urllib3,mutagen,pyjnius
orientation = portrait, landscape
fullscreen = 0
android.permissions = INTERNET
android.api = 35
android.minapi = 29
android.archs = arm64-v8a
android.accept_sdk_license = True
android.debug_artifact = apk
android.numeric_version = 1005
android.add_src = native
android.add_assets = startup/_load.html:_load.html,web/logo.png:startup-logo.png
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/icon.png
presplash.color = #101114
p4a.bootstrap = webview
p4a.hook = startup_hook.py
[buildozer]
log_level = 2
warn_on_root = 1

