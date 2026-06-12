"""
RF Scanner Cloud Server v2
- Receives WiFi scan data pushed from Android app
- Serves per-device view + shared dashboard
- Runs DNN inference server-side (no TF on phone)
"""

from flask import Flask, jsonify, request, render_template_string, send_file
import json, os, time
from datetime import datetime
from collections import defaultdict
import numpy as np

# ── DNN models (optional) ───────────────────────
try:
    from tensorflow import keras
    model           = keras.models.load_model("models/rssi_model.h5")
    direction_model = keras.models.load_model("models/direction_model.h5")
    MODELS_LOADED   = True
    print("✅ DNN models loaded")
except Exception as e:
    MODELS_LOADED = False
    print(f"⚠️  No DNN models: {e}")

app = Flask(__name__)

# ── In-memory store ─────────────────────────────
# { device_id: { networks, tracking, last_seen, timestamp } }
device_store   = {}
# direction history per device
tracking_store = defaultdict(lambda: defaultdict(list))

# ────────────────────────────────────────────────
#  DNN helpers
# ────────────────────────────────────────────────
def predict_signal(rssi):
    if MODELS_LOADED:
        pred = model.predict(np.array([[rssi]]), verbose=0)
        idx  = int(np.argmax(pred))
    else:
        idx = 0 if rssi > -58 else (1 if rssi > -78 else 2)
    return ["Strong 🔥", "Medium ⚠️", "Weak ❌"][idx]


def predict_direction(rssi_list):
    if not rssi_list: return "—"
    cur = rssi_list[-1]
    if cur < -95: return "Out of range"
    if cur > -50: return "Near 📍"
    if cur < -80: return "Far 🔭"
    if len(rssi_list) >= 3 and MODELS_LOADED:
        seq = np.array([rssi_list[-3:]])
        idx = int(np.argmax(direction_model.predict(seq, verbose=0)))
        return ["Getting closer ⬆️", "Moving away ⬇️", "Stable ↔️"][idx]
    if len(rssi_list) >= 2:
        return "Getting closer ⬆️" if cur > rssi_list[-2] else "Moving away ⬇️"
    return "Stable ↔️"

# ────────────────────────────────────────────────
#  /device_push  — called by Android app
# ────────────────────────────────────────────────
@app.route("/device_push", methods=["POST"])
def device_push():
    data      = request.get_json(force=True)
    device_id = data.get("device_id", "unknown")
    networks  = data.get("networks", [])

    # Update tracking history on server
    for net in networks:
        ssid = net["SSID"]
        rssi = net["RSSI"]
        tracking_store[device_id][ssid].append(rssi)
        tracking_store[device_id][ssid] = tracking_store[device_id][ssid][-50:]

    # Enrich with DNN + direction
    enriched = []
    for net in networks:
        ssid      = net["SSID"]
        rssi      = net["RSSI"]
        hist      = tracking_store[device_id][ssid]
        net["DNN"]       = predict_signal(rssi)
        net["Direction"] = predict_direction(hist)
        enriched.append(net)

    device_store[device_id] = {
        "networks":   enriched,
        "last_seen":  datetime.now().strftime("%H:%M:%S"),
        "timestamp":  time.time(),
    }

    return jsonify({"status": "ok", "enriched": enriched})

# ────────────────────────────────────────────────
#  /devices  — list all active devices
# ────────────────────────────────────────────────
@app.route("/devices")
def devices():
    now    = time.time()
    result = {}
    for did, info in device_store.items():
        age = int(now - info["timestamp"])
        result[did] = {
            "last_seen":  info["last_seen"],
            "age_seconds": age,
            "active":     age < 120,
            "count":      len(info["networks"]),
        }
    return jsonify(result)

# ────────────────────────────────────────────────
#  /device/<id>  — data for one device
# ────────────────────────────────────────────────
@app.route("/device/<device_id>")
def device_data(device_id):
    info = device_store.get(device_id)
    if not info:
        return jsonify({"error": "Device not found or no data yet"}), 404
    return jsonify({
        "device_id": device_id,
        "networks":  info["networks"],
        "last_seen": info["last_seen"],
    })

# ────────────────────────────────────────────────
#  /dashboard_data  — all devices combined
# ────────────────────────────────────────────────
@app.route("/dashboard_data")
def dashboard_data():
    now    = time.time()
    active = {
        did: info for did, info in device_store.items()
        if now - info["timestamp"] < 120
    }
    return jsonify({
        "devices":      len(active),
        "device_list":  list(active.keys()),
        "store":        {
            did: {
                "networks":  info["networks"],
                "last_seen": info["last_seen"],
            }
            for did, info in active.items()
        },
        "dnn": MODELS_LOADED,
    })

# ────────────────────────────────────────────────
#  /export
# ────────────────────────────────────────────────
@app.route("/export")
def export_all():
    path = "/tmp/rf_export.json"
    with open(path, "w") as f:
        json.dump({
            "exported_at": datetime.now().isoformat(),
            "devices":     {
                did: info["networks"]
                for did, info in device_store.items()
            }
        }, f, indent=2)
    return send_file(path, as_attachment=True)

# ────────────────────────────────────────────────
#  /  — Shared Dashboard UI
# ────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RF Scanner Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@300;600;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#060d1a;--surface:#0c1829;--border:#1a3a5c;
  --cyan:#00e5ff;--purple:#b400ff;--green:#00ff90;
  --yellow:#ffe600;--red:#ff3355;--text:#c8daf0;--sub:#3a6a8a}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Exo 2',sans-serif;padding:14px;min-height:100vh}
h1{font-size:clamp(1.3rem,4vw,2rem);font-weight:800;text-align:center;letter-spacing:.1em;
   background:linear-gradient(90deg,var(--cyan),var(--purple));
   -webkit-background-clip:text;-webkit-text-fill-color:transparent;padding:14px 0 4px}
.sub{text-align:center;color:var(--sub);font-size:.8rem;letter-spacing:.2em;text-transform:uppercase;margin-bottom:16px}

.toolbar{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-bottom:14px}
button{font-family:'Exo 2',sans-serif;font-weight:600;font-size:.88rem;padding:9px 20px;
       border-radius:6px;cursor:pointer;transition:all .2s;border:none;letter-spacing:.04em}
.btn-scan  {background:var(--cyan);color:#000}
.btn-scan:hover{filter:brightness(1.15);box-shadow:0 0 18px var(--cyan)}
.btn-export{background:transparent;color:var(--purple);border:1.5px solid var(--purple)}
.btn-export:hover{background:var(--purple);color:#fff}

.status{text-align:center;padding:7px;margin-bottom:14px;font-size:.85rem;
        font-family:'Share Tech Mono',monospace;border-radius:6px;transition:all .3s}
.s-ready  {color:var(--cyan);background:rgba(0,229,255,.06);border:1px solid rgba(0,229,255,.2)}
.s-loading{color:var(--yellow);background:rgba(255,230,0,.06);border:1px solid rgba(255,230,0,.2)}
.s-ok     {color:var(--green);background:rgba(0,255,144,.06);border:1px solid rgba(0,255,144,.2)}
.s-error  {color:var(--red);background:rgba(255,51,85,.06);border:1px solid rgba(255,51,85,.2)}

.stat-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:16px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center}
.sv{font-size:1.5rem;font-weight:800;font-family:'Share Tech Mono',monospace;color:var(--cyan)}
.sl{font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:var(--sub);margin-top:3px}

.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
      padding:16px;margin-bottom:16px;overflow:hidden}
.card-title{font-size:.9rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
            color:var(--cyan);margin-bottom:12px;display:flex;align-items:center;gap:8px}

/* Device tabs */
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.tab{padding:6px 14px;border-radius:20px;font-size:.8rem;cursor:pointer;
     border:1.5px solid var(--border);background:transparent;color:var(--sub);transition:all .2s}
.tab.active{border-color:var(--cyan);color:var(--cyan);background:rgba(0,229,255,.08)}
.tab.offline{border-color:#2a3a4a;color:#2a3a4a}

.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;min-width:420px}
th{padding:9px 10px;text-align:left;font-size:.74rem;letter-spacing:.07em;text-transform:uppercase;
   color:var(--cyan);background:rgba(0,229,255,.07);border-bottom:1px solid var(--border)}
td{padding:10px 10px;font-size:.83rem;border-bottom:1px solid rgba(255,255,255,.04);
   font-family:'Share Tech Mono',monospace}
tr:hover td{background:rgba(180,0,255,.08)}
.no-data{text-align:center;padding:28px;color:#2a4a6a;font-style:italic;font-family:'Exo 2',sans-serif}

.pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.75rem}
.p-s{background:rgba(0,255,144,.1);color:#00ff90;border:1px solid #00ff90}
.p-m{background:rgba(255,230,0,.1);color:#ffe600;border:1px solid #ffe600}
.p-w{background:rgba(255,51,85,.1);color:#ff3355;border:1px solid #ff3355}

.bar{display:inline-block;height:7px;border-radius:3px;vertical-align:middle;margin-right:5px}
.chart-box{height:260px;position:relative}

.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:.72rem;margin-left:6px}
.b-dnn{background:rgba(180,0,255,.15);border:1px solid var(--purple);color:var(--purple)}
.b-live{background:rgba(0,255,144,.12);border:1px solid var(--green);color:var(--green)}

/* install card */
.install-card{background:rgba(180,0,255,.07);border:1px solid rgba(180,0,255,.3);
              border-radius:12px;padding:16px;margin-bottom:16px;text-align:center}
.install-card h3{color:var(--purple);margin-bottom:8px;font-size:1rem}
.install-card p{color:var(--sub);font-size:.85rem;line-height:1.6;margin-bottom:10px}
.steps{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin:10px 0}
.step{background:var(--surface);border:1px solid var(--border);border-radius:8px;
      padding:10px 14px;font-size:.82rem;color:var(--text);min-width:140px;text-align:center}
.step-num{font-size:1.1rem;color:var(--cyan);font-weight:800;display:block;margin-bottom:4px}

@media(max-width:480px){
  .card{padding:12px 8px}
  td,th{padding:8px 6px;font-size:.78rem}
}
</style>
</head>
<body>
<h1>⟁ RF SCANNER</h1>
<p class="sub">Multi-Device WiFi Intelligence Dashboard</p>

<!-- Install instructions -->
<div class="install-card">
  <h3>📱 Scan from your phone or laptop</h3>
  <p>Install the RF Scanner app on your Android device to see your real nearby WiFi networks with RSSI, distance, direction & AI signal quality.</p>
  <div class="steps">
    <div class="step"><span class="step-num">1</span>Download APK below</div>
    <div class="step"><span class="step-num">2</span>Install on Android</div>
    <div class="step"><span class="step-num">3</span>Enter this page's URL in the app</div>
    <div class="step"><span class="step-num">4</span>Tap SCAN — see data here live</div>
  </div>
  <button class="btn-scan" onclick="window.location.href='/download_apk'" style="margin-top:6px">⬇ Download APK</button>
</div>

<div class="toolbar">
  <button class="btn-scan" onclick="loadDashboard()">⟳ REFRESH</button>
  <button class="btn-export" onclick="window.location.href='/export'">⬇ EXPORT ALL</button>
</div>

<div id="statusBar" class="status s-ready">Waiting for data…</div>

<div class="stat-row">
  <div class="stat"><div class="sv" id="sDevices">0</div><div class="sl">Active Devices</div></div>
  <div class="stat"><div class="sv" id="sTotal">—</div><div class="sl">Networks</div></div>
  <div class="stat"><div class="sv" id="sStrong">—</div><div class="sl">Strong</div></div>
  <div class="stat"><div class="sv" id="sTime">—</div><div class="sl">Last Update</div></div>
</div>

<div class="card">
  <div class="card-title">📱 Devices <span id="dnnBadge"></span></div>
  <div class="tabs" id="deviceTabs"></div>
  <div class="table-wrap"><table id="netTable"><tr><td class="no-data">No device data yet — open the app and scan</td></tr></table></div>
</div>

<div class="card">
  <div class="card-title">📈 RSSI Graph</div>
  <div class="chart-box"><canvas id="rssiChart"></canvas></div>
</div>

<script>
let chart, activeDevice=null, allData={};
const COLORS=['#00e5ff','#b400ff','#00ff90','#ffe600','#ff3355','#ff8800'];
let ci=0;

function initChart(){
  chart=new Chart(document.getElementById('rssiChart'),{
    type:'line',data:{labels:[],datasets:[]},
    options:{responsive:true,maintainAspectRatio:false,animation:{duration:300},
      plugins:{legend:{labels:{color:'#c8daf0',font:{family:"'Exo 2'"}}}},
      scales:{
        y:{min:-100,max:-30,grid:{color:'rgba(26,58,92,.5)'},
           ticks:{color:'#5a7a99',callback:v=>v+' dBm'}},
        x:{grid:{color:'rgba(26,58,92,.3)'},ticks:{color:'#5a7a99'}}
      }}
  });
}

function setStatus(msg,cls){
  const el=document.getElementById('statusBar');
  el.textContent=msg; el.className='status '+cls;
}

function bar(rssi){
  const w=Math.max(0,Math.min(90,((rssi+100)/70)*90));
  const c=rssi>=-55?'#00ff90':rssi>=-70?'#ffe600':'#ff3355';
  return `<span class="bar" style="width:${w}px;background:${c}"></span>`;
}
function pill(s){
  const m={Strong:'p-s',Medium:'p-m',Weak:'p-w'};
  return `<span class="pill ${m[s]||'p-w'}">${s}</span>`;
}

async function loadDashboard(){
  setStatus('Refreshing…','s-loading');
  try{
    const r=await fetch('/dashboard_data');
    const d=await r.json();
    allData=d.store||{};

    document.getElementById('dnnBadge').innerHTML=
      d.dnn?'<span class="badge b-dnn">DNN ✓</span>':'';

    // device count
    const devCount=Object.keys(allData).length;
    document.getElementById('sDevices').textContent=devCount;
    document.getElementById('sTime').textContent=new Date().toLocaleTimeString();

    // tabs
    const tabsEl=document.getElementById('deviceTabs');
    tabsEl.innerHTML='';
    if(devCount===0){
      tabsEl.innerHTML='<span style="color:var(--sub);font-size:.82rem">No active devices</span>';
      document.getElementById('netTable').innerHTML=
        '<tr><td class="no-data">Open the RF Scanner app on your phone and scan</td></tr>';
      document.getElementById('sTotal').textContent='—';
      document.getElementById('sStrong').textContent='—';
      setStatus('No devices connected yet','s-loading');
      return;
    }

    Object.keys(allData).forEach((did,i)=>{
      const btn=document.createElement('button');
      btn.className='tab'+(i===0||did===activeDevice?' active':'');
      btn.textContent=`📱 ${did}`;
      btn.onclick=()=>{ activeDevice=did; renderDevice(did); 
        document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
        btn.classList.add('active');
      };
      tabsEl.appendChild(btn);
    });

    if(!activeDevice||!allData[activeDevice])
      activeDevice=Object.keys(allData)[0];
    renderDevice(activeDevice);

    setStatus(`${devCount} device(s) active — auto-refreshing every 15s`,'s-ok');
  }catch(e){
    console.error(e);
    setStatus('Refresh failed','s-error');
  }
}

function renderDevice(did){
  const info=allData[did];
  if(!info){return;}
  const nets=info.networks||[];

  const strong=nets.filter(n=>n.RSSI>=-55).length;
  document.getElementById('sTotal').textContent=nets.length;
  document.getElementById('sStrong').textContent=strong;

  let html=`<tr><th>SSID</th><th>RSSI</th><th>Distance</th><th>Direction</th>
            <th>DNN</th><th>Band</th><th>Security</th><th>Strength</th></tr>`;
  nets.forEach(n=>{
    html+=`<tr>
      <td>${n.SSID}</td>
      <td>${bar(n.RSSI)}${n.RSSI} dBm</td>
      <td>${n.Distance} m</td>
      <td>${n.Direction||'—'}</td>
      <td>${n.DNN||'—'}</td>
      <td>${n.Band}</td>
      <td>${n.Security}</td>
      <td>${pill(n.Strength)}</td>
    </tr>`;
    if(n.RSSI>-78){
      let ds=chart.data.datasets.find(x=>x.label===`${did}:${n.SSID}`);
      if(!ds){
        const c=COLORS[ci++%COLORS.length];
        ds={label:`${did}:${n.SSID}`,data:[],borderColor:c,
            backgroundColor:c+'22',borderWidth:2.5,tension:.4,pointRadius:4};
        chart.data.datasets.push(ds);
      }
      ds.data.push(n.RSSI);
      if(ds.data.length>30)ds.data.shift();
    }
  });
  document.getElementById('netTable').innerHTML=html;

  const maxLen=Math.max(...chart.data.datasets.map(d=>d.data.length),0);
  chart.data.labels=Array.from({length:maxLen},(_,i)=>i+1);
  chart.update();
}

window.onload=()=>{initChart();loadDashboard();setInterval(loadDashboard,15000)};
</script>
</body>
</html>
""")

# APK download placeholder
@app.route("/download_apk")
def download_apk():
    apk_path = "rf_scanner.apk"
    if os.path.exists(apk_path):
        return send_file(apk_path, as_attachment=True)
    return """
    <html><body style="background:#060d1a;color:#00e5ff;font-family:monospace;padding:40px;text-align:center">
    <h2>APK not yet built</h2>
    <p style="color:#5a7a99;margin-top:16px">
      Build the APK with Buildozer, place <b>rf_scanner.apk</b> in the server folder,<br>
      then users can download it directly from this page.
    </p>
    <p style="margin-top:20px"><a href="/" style="color:#b400ff">← Back to Dashboard</a></p>
    </body></html>
    """, 200


if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    print(f"🚀 RF Scanner Server v2 | DNN={MODELS_LOADED}")
    app.run(host="0.0.0.0", port=port, debug=debug)
