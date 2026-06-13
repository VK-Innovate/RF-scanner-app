[app]
title = RF Scanner
package.name = rfscanner
package.domain = org.rfscanner
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0

requirements = python3,kivy==2.2.0,requests,android,pyjnius

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_STATE,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

android.minapi = 26
android.targetapi = 33
android.api = 33
android.ndk = 27.3.13750724
android.build_tools_version = 33.0.2
android.accept_sdk_license = True
android.skip_update = False
android.archs = arm64-v8a

android.allow_backup = True
android.presplash_color = #060d1a
orientation = portrait
fullscreen = 0

log_level = 2
warn_on_root = 1
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1