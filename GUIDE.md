# RF Scanner v2 — Full Guide

## Architecture

```
┌─────────────────────────────────────────────┐
│         Android App (Kivy APK)              │
│  - Scans real WiFi via Android WifiManager  │
│  - Shows RSSI, distance, direction, DNN     │
│  - Pushes data to cloud server every 30s    │
└──────────────────┬──────────────────────────┘
                   │  POST /device_push
                   ▼
┌─────────────────────────────────────────────┐
│         Cloud Server (Flask)                │
│  - Runs DNN inference (server-side)         │
│  - Stores data per device                   │
│  - Serves shared dashboard                  │
└──────────────────┬──────────────────────────┘
                   │  Browser opens URL
                   ▼
┌─────────────────────────────────────────────┐
│    Dashboard (any browser, phone/laptop)    │
│  - See all devices' WiFi scans live         │
│  - Switch between device views              │
│  - RSSI graph, export JSON                  │
└─────────────────────────────────────────────┘
```

---

## Step 1 — Deploy the Server (Render.com, free)

1. Push `server/` folder to GitHub
2. Go to render.com → New Web Service → connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
5. Your URL: `https://rf-scanner.onrender.com`

---

## Step 2 — Build the Android APK

### Prerequisites (Ubuntu/Linux recommended)
```bash
# Install system dependencies
sudo apt update
sudo apt install -y python3-pip git zip unzip openjdk-17-jdk autoconf \
  libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
  libtinfo5 cmake libffi-dev libssl-dev

# Install buildozer
pip install buildozer cython

# Go to android_app folder
cd android_app

# First build (takes 20-40 min, downloads Android SDK/NDK)
buildozer android debug

# APK will be at:
# android_app/bin/rfscanner-1.0-debug.apk
```

### Copy APK to server folder
```bash
cp bin/rfscanner-1.0-debug.apk ../server/rf_scanner.apk
```
Now users can download it directly from `https://your-server.onrender.com/download_apk`

---

## Step 3 — User Flow

1. User opens `https://your-server.onrender.com` on their phone/laptop browser
2. Sees the dashboard with "Download APK" button
3. Downloads and installs the APK (Android: Settings → Allow unknown sources)
4. Opens app → enters server URL → taps SCAN
5. Their WiFi data appears on the dashboard live

---

## File Structure

```
rf_scanner_v2/
├── android_app/
│   ├── main.py          ← Kivy Android app
│   └── buildozer.spec   ← APK build config
└── server/
    ├── app.py           ← Flask cloud server
    ├── requirements.txt
    ├── Procfile
    └── models/          ← (optional) DNN .h5 files
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Shared dashboard UI |
| `/device_push` | POST | Android app sends scan data |
| `/dashboard_data` | GET | All active devices JSON |
| `/device/<id>` | GET | One device's data |
| `/devices` | GET | List of active devices |
| `/export` | GET | Download all data as JSON |
| `/download_apk` | GET | Download the APK file |

---

## Tips

- **Multiple users**: each device gets a unique ID automatically, stored on the phone
- **DNN on server**: TensorFlow runs server-side — no heavy ML on the phone
- **Auto-refresh**: app scans every 30s; dashboard refreshes every 15s
- **Offline**: app stores last scan, works without internet for local display
- **iOS**: not supported with this approach (Apple blocks WiFi scanning APIs)
