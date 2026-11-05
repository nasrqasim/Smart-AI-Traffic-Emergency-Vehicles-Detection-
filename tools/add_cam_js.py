import os

target = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static", "app.js")
with open(target, "r", encoding="utf-8") as f:
    js = f.read()

cam_client_code = '''
// ==========================================
// Laptop Camera / External Webcam / CCTV Integration
// ==========================================
let webcamStream = null;
let webcamVideoElem = null;
let webcamCanvasElem = null;
let webcamInterval = null;

const camSelect = $('camSourceSelect');
const btnToggleCam = $('btnToggleCamera');
const camStatus = $('camStatusMsg');
const rtspBox = $('rtspInputBox');

if (camSelect) {
  camSelect.onchange = () => {
    if (camSelect.value === 'rtsp') {
      rtspBox.style.display = 'block';
      camStatus.innerHTML = 'Enter your <b>RTSP CCTV Stream URL</b> above and click connect.';
    } else {
      rtspBox.style.display = 'none';
      if (camSelect.value === 'webcam') {
        camStatus.innerHTML = 'Click <b>Start Camera</b> to activate your laptop/USB webcam.';
      } else {
        camStatus.innerHTML = 'Showing recorded <b>traffic footage</b> demonstration.';
      }
    }
  };
}

if (btnToggleCam) {
  btnToggleCam.onclick = async () => {
    if (webcamStream) {
      // Stop webcam
      stopLaptopCamera();
      btnToggleCam.textContent = 'Start Camera';
      btnToggleCam.style.background = '#205244';
      camStatus.textContent = 'Laptop webcam disconnected.';
    } else {
      // Start webcam
      await startLaptopCamera();
    }
  };
}

const btnRtsp = $('btnConnectRtsp');
if (btnRtsp) {
  btnRtsp.onclick = async () => {
    const url = $('rtspUrl').value.trim();
    if (!url) {
      alert('Please enter a valid RTSP stream URL');
      return;
    }
    camStatus.textContent = 'Connecting to RTSP CCTV Stream...';
    try {
      const res = await fetch('/api/vision/source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: url })
      });
      const data = await res.json();
      if (data.ok) {
        camStatus.innerHTML = '<span style="color:#a5f3ce;">Connected to CCTV Stream: ' + url + '</span>';
      } else {
        camStatus.textContent = 'RTSP Error: ' + (data.error || 'Connection failed');
      }
    } catch (e) {
      camStatus.textContent = 'Connection error: ' + e.message;
    }
  };
}

async function startLaptopCamera() {
  try {
    camStatus.textContent = 'Requesting browser camera permission...';
    webcamStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 768 }, height: { ideal: 432 }, facingMode: 'user' },
      audio: false
    });

    if (!webcamVideoElem) {
      webcamVideoElem = document.createElement('video');
      webcamVideoElem.autoplay = true;
      webcamVideoElem.playsInline = true;
      webcamVideoElem.style.display = 'none';
      document.body.appendChild(webcamVideoElem);
    }
    webcamVideoElem.srcObject = webcamStream;
    await webcamVideoElem.play();

    if (!webcamCanvasElem) {
      webcamCanvasElem = document.createElement('canvas');
      webcamCanvasElem.width = 768;
      webcamCanvasElem.height = 432;
    }

    btnToggleCam.textContent = 'Stop Camera';
    btnToggleCam.style.background = '#7d2020';
    camStatus.innerHTML = '<span style="color:#a5f3ce;">Laptop camera streaming live! YOLOv8 active.</span>';

    // Stream frames to server at ~8 FPS
    const canvasCtx = webcamCanvasElem.getContext('2d');
    webcamInterval = setInterval(async () => {
      if (!webcamStream || webcamVideoElem.readyState < 2) return;
      canvasCtx.drawImage(webcamVideoElem, 0, 0, 768, 432);
      const b64 = webcamCanvasElem.toDataURL('image/jpeg', 0.65);
      try {
        await fetch('/api/vision/upload_frame', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: b64 })
        });
      } catch (err) {}
    }, 125);

  } catch (err) {
    camStatus.innerHTML = '<span style="color:#ff8888;">Camera access error: ' + err.message + '</span>';
    stopLaptopCamera();
  }
}

function stopLaptopCamera() {
  if (webcamInterval) {
    clearInterval(webcamInterval);
    webcamInterval = null;
  }
  if (webcamStream) {
    webcamStream.getTracks().forEach(t => t.stop());
    webcamStream = null;
  }
}
'''

if "Laptop Camera / External Webcam / CCTV Integration" not in js:
    js += "\n" + cam_client_code
    with open(target, "w", encoding="utf-8") as f:
        f.write(js)
    print("Added webcam streaming JS to app.js!")
else:
    print("Webcam streaming JS already present")
