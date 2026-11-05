import os

target = os.path.join(os.path.dirname(__file__), "..", "dashboard", "templates", "index.html")
with open(target, "r", encoding="utf-8") as f:
    html = f.read()

camera_ui = '''        <!-- Live Camera Source Selector & Connect -->
        <div style="margin-bottom:12px; background:#122027; border:1px solid #284148; border-radius:8px; padding:12px;">
          <label style="font-size:10px; color:#8fa8ae; display:block; margin-bottom:6px;">Camera Input Source:</label>
          <div style="display:flex; gap:6px;">
            <select id="camSourceSelect" style="flex:1; font-size:11px; padding:6px; background:#182e36; color:#a5f3ce; border:1px solid #36555f; border-radius:6px;">
              <option value="webcam">💻 My Laptop / USB Webcam</option>
              <option value="sample" selected>🎥 Sample Traffic Footage</option>
              <option value="rtsp">🌐 External CCTV / IP Stream (RTSP)</option>
            </select>
            <button id="btnToggleCamera" style="background:#205244; color:#a5f3ce; border:1px solid #3c7d6b; border-radius:6px; padding:6px 12px; font-size:11px; font-weight:600; cursor:pointer;">Start Camera</button>
          </div>
          <div id="rtspInputBox" style="display:none; margin-top:8px;">
            <input type="text" id="rtspUrl" placeholder="rtsp://192.168.1.100:554/stream" style="width:100%; box-sizing:border-box; font-size:11px; padding:6px; background:#0d181c; color:#fff; border:1px solid #36555f; border-radius:4px;">
            <button id="btnConnectRtsp" style="width:100%; margin-top:6px; background:#1a3d34; color:#9ef3c6; border:1px solid #3b6b5d; border-radius:4px; padding:6px; font-size:10px; cursor:pointer;">Connect CCTV Stream</button>
          </div>
          <div id="camStatusMsg" style="font-size:10px; color:#8fa8ae; margin-top:6px;">Click <b>Start Camera</b> to stream your laptop/USB webcam live into the system.</div>
        </div>
'''

if "camSourceSelect" not in html:
    needle = '<div class="cam-gauges">'
    idx = html.find(needle)
    html = html[:idx] + camera_ui + "\n        " + html[idx:]
    with open(target, "w", encoding="utf-8") as f:
        f.write(html)
    print("Added camera source controls to index.html!")
else:
    print("camSourceSelect already present")
