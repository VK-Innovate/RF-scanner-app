"""
RF Scanner Android App
- Scans real WiFi using Android WifiManager via Pyjnius
- Shows RSSI, distance, direction, DNN signal quality
- Pushes data to cloud server every 30s
- Receives DNN results back from server
"""

import kivy
kivy.require('2.2.0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex

import threading
import requests
import json
import time
import uuid
import os
from datetime import datetime

# ── Colors ──────────────────────────────────────
BG       = get_color_from_hex("#060d1a")
SURFACE  = get_color_from_hex("#0c1829")
CYAN     = get_color_from_hex("#00e5ff")
PURPLE   = get_color_from_hex("#b400ff")
GREEN    = get_color_from_hex("#00ff90")
YELLOW   = get_color_from_hex("#ffe600")
RED      = get_color_from_hex("#ff3355")
TEXT     = get_color_from_hex("#c8daf0")
SUBTEXT  = get_color_from_hex("#3a6a8a")

# ── Device ID (persistent per device) ──────────
DEVICE_ID_FILE = "/sdcard/rf_scanner_device_id.txt"
def get_device_id():
    if os.path.exists(DEVICE_ID_FILE):
        with open(DEVICE_ID_FILE) as f:
            return f.read().strip()
    did = "device_" + str(uuid.uuid4())[:8]
    with open(DEVICE_ID_FILE, "w") as f:
        f.write(did)
    return did

DEVICE_ID = get_device_id()

# ── WiFi Scanner using Android WifiManager ──────
def scan_wifi_android():
    """Uses Pyjnius to access Android WifiManager for real WiFi scan."""
    try:
        from jnius import autoclass, cast
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.ACCESS_FINE_LOCATION,
            Permission.ACCESS_COARSE_LOCATION,
            Permission.ACCESS_WIFI_STATE,
            Permission.CHANGE_WIFI_STATE,
        ])

        Context      = autoclass('android.content.Context')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity     = PythonActivity.mActivity
        wifi_service = activity.getSystemService(Context.WIFI_SERVICE)
        wifi_manager = cast('android.net.wifi.WifiManager', wifi_service)

        wifi_manager.startScan()
        time.sleep(2)
        results = wifi_manager.getScanResults()

        networks = []
        seen     = set()
        for r in results:
            ssid  = str(r.SSID) if r.SSID else "Hidden"
            bssid = str(r.BSSID)
            if ssid in seen:
                continue
            seen.add(ssid)

            rssi      = int(r.level)
            freq      = int(r.frequency)
            band      = "5 GHz" if freq > 3000 else "2.4 GHz"
            channel   = freq_to_channel(freq)
            distance  = round(10 ** ((-40 - rssi) / 30), 2)
            strength  = "Strong" if rssi >= -55 else ("Medium" if rssi >= -70 else "Weak")
            cap       = str(r.capabilities)
            security  = "WPA3" if "SAE" in cap else ("WPA2" if "WPA2" in cap else ("WPA" if "WPA" in cap else "Open"))

            networks.append({
                "SSID":     ssid,
                "BSSID":    bssid,
                "RSSI":     rssi,
                "Distance": distance,
                "Band":     band,
                "Channel":  channel,
                "Security": security,
                "Strength": strength,
            })

        return sorted(networks, key=lambda x: x["RSSI"], reverse=True)

    except Exception as e:
        print(f"[WiFi] Error: {e}")
        return mock_networks()


def freq_to_channel(freq):
    if freq == 2412: return 1
    if freq == 2437: return 6
    if freq == 2462: return 11
    if 5180 <= freq <= 5825:
        return (freq - 5000) // 5
    return "?"


def mock_networks():
    """Fallback mock data when not on Android."""
    import random
    base_nets = [
        ("HomeNetwork_5G",  "AA:BB:CC:11:22:01", -45, "5 GHz",   "36", "WPA2"),
        ("TP-Link_2.4G",    "AA:BB:CC:11:22:02", -62, "2.4 GHz", "6",  "WPA2"),
        ("JioFiber_Mesh",   "AA:BB:CC:11:22:03", -70, "2.4 GHz", "11", "WPA2"),
        ("Airtel_Xstream",  "AA:BB:CC:11:22:04", -55, "5 GHz",   "48", "WPA3"),
        ("BSNL_Office",     "AA:BB:CC:11:22:05", -80, "2.4 GHz", "1",  "WPA"),
        ("Hidden",          "AA:BB:CC:11:22:06", -88, "2.4 GHz", "3",  "WPA2"),
    ]
    nets = []
    for ssid, bssid, base, band, ch, sec in base_nets:
        rssi = int(base + random.gauss(0, 3))
        dist = round(10 ** ((-40 - rssi) / 30), 2)
        nets.append({
            "SSID": ssid, "BSSID": bssid, "RSSI": rssi,
            "Distance": dist, "Band": band, "Channel": ch,
            "Security": sec,
            "Strength": "Strong" if rssi >= -55 else ("Medium" if rssi >= -70 else "Weak"),
        })
    return sorted(nets, key=lambda x: x["RSSI"], reverse=True)


# ── UI Helpers ──────────────────────────────────
def make_label(text, color=None, size=16, bold=False, halign="left"):
    lbl = Label(
        text=text,
        color=color or TEXT,
        font_size=sp(size),
        bold=bold,
        halign=halign,
        size_hint_y=None,
        markup=True,
    )
    lbl.bind(size=lambda *a: setattr(lbl, 'text_size', (lbl.width, None)))
    lbl.bind(texture_size=lambda *a: setattr(lbl, 'height', lbl.texture_size[1] + dp(6)))
    return lbl


def signal_bar(rssi):
    bars = "▂▄▆█"
    if rssi >= -55:   return f"[color=#00ff90]{bars}[/color]"
    if rssi >= -70:   return f"[color=#ffe600]{bars[:3]}[/color][color=#3a5a7a]{bars[3]}[/color]"
    if rssi >= -85:   return f"[color=#ff8800]{bars[:2]}[/color][color=#3a5a7a]{bars[2:]}[/color]"
    return f"[color=#ff3355]{bars[0]}[/color][color=#3a5a7a]{bars[1:]}[/color]"


def strength_color(s):
    return {"Strong": "#00ff90", "Medium": "#ffe600", "Weak": "#ff3355"}.get(s, "#c8daf0")


def dnn_color(d):
    if "Strong" in d: return "#00ff90"
    if "Medium" in d: return "#ffe600"
    return "#ff3355"


# ── Network Card Widget ─────────────────────────
class NetworkCard(BoxLayout):
    def __init__(self, net, direction="—", dnn="—", **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None,
                         padding=dp(12), spacing=dp(4), **kwargs)

        sc = strength_color(net["Strength"])

        with self.canvas.before:
            Color(*get_color_from_hex("#0c1829"))
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._update_rect, size=self._update_rect)

        # SSID row
        top = BoxLayout(size_hint_y=None, height=dp(28))
        top.add_widget(make_label(
            f"[b]{net['SSID']}[/b]", color=CYAN, size=15, bold=True))
        top.add_widget(make_label(
            signal_bar(net["RSSI"]), halign="right", size=18))
        self.add_widget(top)

        # RSSI + distance
        self.add_widget(make_label(
            f"[color={sc}]{net['RSSI']} dBm[/color]   "
            f"[color=#5a7a99]~{net['Distance']} m[/color]   "
            f"[color=#5a7a99]{net['Band']} ch{net['Channel']}[/color]",
            size=13))

        # Direction + DNN
        dc = dnn_color(dnn)
        self.add_widget(make_label(
            f"[color=#b400ff]Direction:[/color] {direction}   "
            f"[color=#b400ff]DNN:[/color] [color={dc}]{dnn}[/color]",
            size=13))

        # BSSID + security
        self.add_widget(make_label(
            f"[color=#2a4a6a]{net['BSSID']}  {net['Security']}[/color]",
            size=11))

        self.height = dp(100)

    def _update_rect(self, *a):
        self.bg_rect.pos  = self.pos
        self.bg_rect.size = self.size


# ── Main Screen ─────────────────────────────────
class ScanScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.networks      = []
        self.tracking_data = {}
        self.server_url    = ""
        self.auto_event    = None
        self._build_ui()

    def _build_ui(self):
        root = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        Window.clearcolor = BG

        # Title
        root.add_widget(make_label(
            "[b]⟁ RF SCANNER[/b]", color=CYAN, size=22, bold=True, halign="center"))
        root.add_widget(make_label(
            f"Device: {DEVICE_ID}", color=SUBTEXT, size=11, halign="center"))

        # Server URL input
        url_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.url_input = TextInput(
            hint_text="Server URL  e.g. https://your-app.onrender.com",
            text="http://10.0.2.2:5000",
            multiline=False,
            size_hint_x=0.75,
            background_color=get_color_from_hex("#0c1829"),
            foreground_color=TEXT,
            hint_text_color=SUBTEXT,
            font_size=sp(12),
        )
        url_row.add_widget(self.url_input)
        save_btn = Button(text="Set", size_hint_x=0.25,
                          background_color=PURPLE, color=(1,1,1,1), font_size=sp(13))
        save_btn.bind(on_press=self.save_url)
        url_row.add_widget(save_btn)
        root.add_widget(url_row)

        # Buttons
        btn_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.scan_btn = Button(text="⟳ SCAN", background_color=CYAN,
                               color=(0,0,0,1), font_size=sp(14), bold=True)
        self.scan_btn.bind(on_press=lambda *a: self.do_scan())
        self.auto_btn = Button(text="▶ AUTO", background_color=get_color_from_hex("#0c3a1a"),
                               color=GREEN, font_size=sp(13))
        self.auto_btn.bind(on_press=self.toggle_auto)
        self.dash_btn = Button(text="🌐 Dashboard", background_color=get_color_from_hex("#1a003a"),
                               color=PURPLE, font_size=sp(13))
        self.dash_btn.bind(on_press=self.open_dashboard)
        btn_row.add_widget(self.scan_btn)
        btn_row.add_widget(self.auto_btn)
        btn_row.add_widget(self.dash_btn)
        root.add_widget(btn_row)

        # Status
        self.status_lbl = make_label("Ready — tap SCAN", color=SUBTEXT, size=12, halign="center")
        root.add_widget(self.status_lbl)

        # Stats row
        stats_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
        self.stat_total  = self._stat_box("—", "Networks")
        self.stat_strong = self._stat_box("—", "Strong")
        self.stat_best   = self._stat_box("—", "Best RSSI")
        stats_row.add_widget(self.stat_total)
        stats_row.add_widget(self.stat_strong)
        stats_row.add_widget(self.stat_best)
        root.add_widget(stats_row)

        # Scroll list
        self.scroll = ScrollView(size_hint=(1, 1))
        self.net_list = BoxLayout(orientation='vertical', spacing=dp(6),
                                  size_hint_y=None, padding=[0, dp(4)])
        self.net_list.bind(minimum_height=self.net_list.setter('height'))
        self.scroll.add_widget(self.net_list)
        root.add_widget(self.scroll)

        self.add_widget(root)

    def _stat_box(self, val, lbl):
        box = BoxLayout(orientation='vertical')
        val_lbl = make_label(val, color=CYAN, size=18, bold=True, halign="center")
        lbl_lbl = make_label(lbl, color=SUBTEXT, size=10, halign="center")
        box.add_widget(val_lbl)
        box.add_widget(lbl_lbl)
        box._val_lbl = val_lbl
        return box

    def save_url(self, *a):
        self.server_url = self.url_input.text.strip().rstrip("/")
        self.status_lbl.text = f"Server set: {self.server_url}"
        self.status_lbl.color = GREEN

    def do_scan(self):
        self.status_lbl.text  = "Scanning…"
        self.status_lbl.color = YELLOW
        self.scan_btn.disabled = True
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        networks = scan_wifi_android()
        # push to server + get DNN results back
        enriched = self._push_to_server(networks)
        Clock.schedule_once(lambda dt: self._update_ui(enriched or networks))

    def _push_to_server(self, networks):
        if not self.server_url:
            return None
        try:
            # compute direction locally
            strong = []
            for net in networks:
                if net["RSSI"] > -78:
                    ssid = net["SSID"]
                    self.tracking_data.setdefault(ssid, []).append(net["RSSI"])
                    self.tracking_data[ssid] = self.tracking_data[ssid][-50:]

            payload = {
                "device_id": DEVICE_ID,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "networks":  networks,
                "tracking":  self.tracking_data,
            }
            r = requests.post(
                f"{self.server_url}/device_push",
                json=payload, timeout=8
            )
            return r.json().get("enriched", networks)
        except Exception as e:
            print(f"[Server] Push failed: {e}")
            return None

    def _update_ui(self, networks):
        self.networks = networks
        self.net_list.clear_widgets()

        strong_count = sum(1 for n in networks if n["RSSI"] >= -55)
        best         = networks[0]["RSSI"] if networks else "—"

        self.stat_total._val_lbl.text  = str(len(networks))
        self.stat_strong._val_lbl.text = str(strong_count)
        self.stat_best._val_lbl.text   = f"{best}"

        for net in networks:
            direction = net.get("Direction", "—")
            dnn       = net.get("DNN", "—")
            card      = NetworkCard(net, direction=direction, dnn=dnn)
            self.net_list.add_widget(card)

        ts = datetime.now().strftime("%H:%M:%S")
        self.status_lbl.text  = f"✓ {len(networks)} networks — {ts}"
        self.status_lbl.color = GREEN
        self.scan_btn.disabled = False

    def toggle_auto(self, *a):
        if self.auto_event:
            self.auto_event.cancel()
            self.auto_event = None
            self.auto_btn.text             = "▶ AUTO"
            self.auto_btn.background_color = get_color_from_hex("#0c3a1a")
        else:
            self.auto_event = Clock.schedule_interval(lambda dt: self.do_scan(), 30)
            self.auto_btn.text             = "⏹ STOP"
            self.auto_btn.background_color = RED
            self.do_scan()

    def open_dashboard(self, *a):
        try:
            from android import open_url
            open_url(self.server_url or "http://10.0.2.2:5000")
        except Exception:
            self.status_lbl.text = "Set server URL first, then tap Dashboard"


# ── App Entry ───────────────────────────────────
class RFScannerApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(ScanScreen(name='scan'))
        return sm


if __name__ == "__main__":
    RFScannerApp().run()
