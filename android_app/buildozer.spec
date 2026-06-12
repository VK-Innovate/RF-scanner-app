[app]
title = RF Scanner
package.name = rfscanner
package.domain = org.rfscanner
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0

# ── Requirements ────────────────────────────────
# Do NOT add tensorflow here — too large for mobile
# DNN inference is done server-side
requirements = python3,kivy==2.2.0,requests,android,pyjnius

# ── Permissions ─────────────────────────────────
android.permissions = \
    INTERNET, \
    ACCESS_NETWORK_STATE, \
    ACCESS_WIFI_STATE, \
    CHANGE_WIFI_STATE, \
    ACCESS_FINE_LOCATION, \
    ACCESS_COARSE_LOCATION, \
    WRITE_EXTERNAL_STORAGE, \
    READ_EXTERNAL_STORAGE

# ── Android settings ────────────────────────────
android.minapi = 26
android.targetapi = 33
android.ndk = 25b
android.sdk = 33
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

# ── App appearance ──────────────────────────────
android.presplash_color = #060d1a
android.icon.filename = %(source.dir)s/icon.png
orientation = portrait
fullscreen = 0

# ── Build ────────────────────────────────────────
log_level = 2
warn_on_root = 1
android.logcat_filters = *:S python:D
