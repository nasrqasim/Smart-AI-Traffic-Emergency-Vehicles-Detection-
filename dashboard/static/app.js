'use strict';
const $ = id => document.getElementById(id), canvas = $('scene'), ctx = canvas.getContext('2d');
let state = null, previous = new Map(), positions = new Map(), receivedAt = 0, blendDuration = 200, paused = false, lastTime = -1, history = [];
const names = { N: 'North', S: 'South', E: 'East', W: 'West' };
const order = ['N', 'E', 'S', 'W'];

$('signals').innerHTML = order.map(p => `
  <div class="signal-tile" id="tile${p}">
    <div class="signal-lamps">
      <i class="red" id="red${p}"></i>
      <i class="yellow" id="yellow${p}"></i>
      <i class="green" id="green${p}"></i>
    </div>
    <div>
      <strong>${names[p].toUpperCase()}</strong>
      <small id="status${p}">CONNECTING</small>
    </div>
  </div>
`).join('');

$('lanes').innerHTML = Object.entries(names).map(([k, n]) => `
  <div class="lane">
    <div class="label">
      <span>${n} ${k === 'S' ? '<b style="color:#ffab00;">(Priority Line)</b>' : ''}</span>
      <span id="count${k}">0 vehicles</span>
    </div>
    <div class="bar">
      <i id="bar${k}" style="width:0%"></i>
    </div>
  </div>
`).join('');

async function control(data) {
  try {
    const r = await fetch('/api/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!r.ok) throw Error((await r.json()).error);
    $('feedback').textContent = data.road ? 'Vehicle queued for insertion.' : 'Control updated.';
  } catch (e) {
    $('feedback').textContent = e.message;
  }
}

// Emergency test button
$('btnEmergencyTest').onclick = async () => {
  try {
    $('feedback').textContent = 'Triggering emergency vehicle preemption...';
    const r = await fetch('/api/vision/trigger_emergency', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approach: 'S', vehicle_type: 'ambulance' })
    });
    const res = await r.json();
    $('feedback').textContent = res.message || 'Ambulance triggered on South approach.';
  } catch (err) {
    $('feedback').textContent = 'Emergency trigger failed: ' + err.message;
  }
};

// View mode switcher (Dual, Twin Only, Camera Only)
$('viewMode').onchange = () => {
  const mode = $('viewMode').value;
  const container = $('sceneContainer');
  const twin = $('twinWrapper');
  const cam = $('cameraWrapper');
  const badge = $('viewBadge');

  if (mode === 'dual') {
    container.className = 'scene scene-dual';
    twin.style.display = 'block';
    cam.style.display = 'flex';
    badge.textContent = 'DUAL VIEW: DIGITAL TWIN + YOLOv8';
  } else if (mode === 'twin') {
    container.className = 'scene';
    twin.style.display = 'block';
    cam.style.display = 'none';
    badge.textContent = 'SUMO DIGITAL TWIN';
  } else {
    container.className = 'scene scene-cam-only';
    twin.style.display = 'none';
    cam.style.display = 'flex';
    badge.textContent = 'LIVE YOLOv8 CAMERA STREAM';
  }
};

$('pause').onclick = () => {
  paused = !paused;
  $('pause').textContent = paused ? 'Resume' : 'Pause';
  control({ paused });
};

$('reset').onclick = () => {
  history = [];
  control({ reset: true });
};

$('fullscreen').onclick = async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.querySelector('.map-panel').requestFullscreen();
  } catch (error) {
    $('feedback').textContent = 'Fullscreen is unavailable in this browser.';
  }
};

$('speed').onchange = () => control({ speed: Number($('speed').value) });
$('controller').onchange = () => control({ controller: $('controller').value });
$('spawn').onclick = () => control({ road: $('road').value, vehicle_type: $('vehicle').value });

async function poll() {
  try {
    const r = await fetch('/api/state', { cache: 'no-store' });
    if (!r.ok) throw Error('Simulator unavailable');
    const d = await r.json();
    if (d.status === 'error') throw Error(d.error);
    if (d.sim_time !== undefined) {
      if (!state || d.sim_time !== state.sim_time) {
        previous = positions;
        positions = new Map(d.vehicles.map(v => [v.id, v]));
        const now = performance.now();
        blendDuration = Math.max(50, Math.min(1000, now - receivedAt));
        receivedAt = now;
      }
      state = d;
      update(d);
    }
    $('connection').textContent = d.status === 'paused' ? 'PAUSED' : d.status === 'starting' ? 'STARTING' : '● LIVE SIMULATION';
  } catch (e) {
    $('connection').textContent = 'OFFLINE';
    $('sceneStatus').textContent = 'SIMULATION DISCONNECTED';
    $('stage').textContent = e.message;
  } finally {
    setTimeout(poll, 150);
  }
}

function update(d) {
  updateSignals(d);
  const t = d.sim_time;
  $('clock').textContent = `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
  $('throughput').textContent = d.throughput_vehicles;
  $('queue').textContent = d.avg_queue_length.toFixed(1);
  $('wait').textContent = d.avg_wait_time_s.toFixed(1);
  $('active').textContent = d.active_vehicles;
  $('pending').textContent = d.pending_vehicles;
  $('collisions').textContent = d.collision_vehicle_events;
  $('teleports').textContent = d.teleported_vehicles;
  $('phase').textContent = d.stage === 'all-red' ? 'ALL APPROACHES STOP' : (names[d.phase] || d.phase).toUpperCase() + ' APPROACH';
  $('countdown').textContent = d.stage === 'green' ? `${d.remaining}s` : '—';
  $('signalStatus').textContent = d.stage === 'green' ? 'Green · opposing approaches stopped' : d.stage === 'yellow' ? 'Yellow · clearing active movements' : 'All red · junction clearance';
  $('stage').textContent = `${d.stage.toUpperCase()} / ${(d.controller || '').replace('_', ' ').toUpperCase()}`;
  $('emergencyAlert').hidden = !d.emergency_preemption;

  // Update Active Rule Banner
  const rule = d.active_rule || 'TRADITIONAL_FALLBACK_60S';
  const banner = $('ruleBanner');
  const tag = $('ruleTag');
  const desc = $('ruleDesc');

  if (rule.includes('EMERGENCY')) {
    banner.className = 'rule-banner emergency';
    tag.textContent = 'RULE 1: EMERGENCY PREEMPTION';
    desc.textContent = '🚨 Emergency Vehicle Override · Swift corridor clearance granted';
  } else if (rule.includes('SOUTH')) {
    banner.className = 'rule-banner south-priority';
    tag.textContent = 'RULE 2: SOUTH LINE DYNAMIC EXTENSION';
    desc.textContent = '⚡ South Line Congestion Priority Active · Dynamically extending green signal';
  } else if (rule.includes('FALLBACK')) {
    banner.className = 'rule-banner fallback-60s';
    tag.textContent = 'RULE 3: 60s TRADITIONAL FALLBACK';
    desc.textContent = '⏱️ Low Traffic / Night Mode · 60s predictable rotation cycle';
  } else {
    banner.className = 'rule-banner';
    tag.textContent = 'RULE 2: DENSITY EXTENSION';
    desc.textContent = 'Actuated green timing allocated to active vehicle demand';
  }

  // Update Camera Approach Density Gauges
  if (d.camera_telemetry && d.camera_telemetry.counts) {
    const cc = d.camera_telemetry.counts;
    $('camCountN').textContent = cc.N || 0;
    $('camCountS').textContent = cc.S || 0;
    $('camCountE').textContent = cc.E || 0;
    $('camCountW').textContent = cc.W || 0;
  }

  // Update policy notes
  $('policyNote').textContent = d.controller === 'vision_actuated'
    ? 'Vision AI 3-Tier Hierarchy: Rule 1 Ambulance Preemption > Rule 2 South Dynamic Extension > Rule 3 60s Traditional Fallback.'
    : d.controller === 'dqn'
    ? 'DQN inference with emergency and maximum green safeguards.'
    : d.controller === 'fixed_time'
    ? 'Webster fixed cycle (20s per road).'
    : 'Density adaptive control with waiting age fairness.';

  // Lane bars
  Object.keys(names).forEach(k => {
    const n = ((d.density[k + '-in'] || 0) + (d.density[k + '-left'] || 0)) * 60;
    $('count' + k).textContent = `${Math.round(n)} vehicles`;
    $('bar' + k).style.width = Math.min(100, n / 120 * 100) + '%';
  });

  if (t < lastTime) {
    history = [];
    previous = new Map();
  }
  if (t !== lastTime) {
    history.push(d.avg_queue_length);
    if (history.length > 240) history.shift();
    drawHistory();
    lastTime = t;
  }
}

function resize(c, g) {
  const r = c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  if (c.width !== Math.round(r.width * dpr) || c.height !== Math.round(r.height * dpr)) {
    c.width = Math.round(r.width * dpr);
    c.height = Math.round(r.height * dpr);
  }
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  return r;
}

function drawHistory() {
  const c = $('history'), g = c.getContext('2d'), r = resize(c, g), w = r.width, h = r.height;
  g.clearRect(0, 0, w, h);
  g.strokeStyle = '#263b42';
  for (let y = 15; y < h; y += 30) {
    g.beginPath();
    g.moveTo(0, y);
    g.lineTo(w, y);
    g.stroke();
  }
  if (history.length < 2) return;
  const max = Math.max(10, ...history);
  g.beginPath();
  history.forEach((v, i) => {
    const x = i / (history.length - 1) * w, y = h - 12 - v / max * (h - 24);
    i ? g.lineTo(x, y) : g.moveTo(x, y);
  });
  g.strokeStyle = '#a5f3ce';
  g.lineWidth = 2;
  g.stroke();
  g.lineTo(w, h);
  g.lineTo(0, h);
  g.closePath();
  const grad = g.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, '#a5f3ce35');
  grad.addColorStop(1, '#a5f3ce00');
  g.fillStyle = grad;
  g.fill();
}

function rect(x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, h);
}

function drawPriorityCorridor() {
  if (!state || state.stage !== 'green') return;
  const c = '#8fefbd19';
  if (state.phase === 'N') rect(243.6, 260.4, 6.4, 240, c);
  if (state.phase === 'E') rect(260.4, 250, 240, 6.4, c);
  if (state.phase === 'S') rect(250, 0, 6.4, 239.6, c);
  if (state.phase === 'W') rect(0, 243.6, 239.6, 6.4, c);
}

function drawRoadLabels(w, h, scale) {
  const labels = [
    ['N', w / 2 - 28 * scale, Math.max(90, h / 2 - 65 * scale)],
    ['S', w / 2 + 28 * scale, Math.min(h - 70, h / 2 + 65 * scale)],
    ['E', Math.min(w - 45, w / 2 + 65 * scale), h / 2 - 25 * scale],
    ['W', Math.max(45, w / 2 - 65 * scale), h / 2 + 25 * scale]
  ];
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const [p, x, y] of labels) {
    const go = state && state.stage === 'green' && state.phase === p;
    ctx.fillStyle = go ? '#a5f3ce' : '#476169';
    ctx.beginPath();
    ctx.arc(x, y, 16, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = go ? '#13382b' : '#bacbcb';
    ctx.font = '600 12px Segoe UI';
    ctx.fillText(p, x, y);
  }
}

function updateSignals(d) {
  if ($('controller').value !== (d.requested_controller || d.controller)) {
    $('controller').value = d.requested_controller || d.controller;
  }
  if (document.activeElement !== $('speed')) { $('speed').value = String(d.speed); }
  paused = d.status === 'paused';
  $('pause').textContent = paused ? 'Resume' : 'Pause';
  let open = [];
  order.forEach((p, i) => {
    const color = (d.signal || '')[i * 4]?.toLowerCase();
    const green = color === 'g', yellow = color === 'y', red = !green && !yellow;
    $('red' + p).classList.toggle('on', red);
    $('yellow' + p).classList.toggle('on', yellow);
    $('green' + p).classList.toggle('on', green);
    $('tile' + p).className = 'signal-tile' + (green ? ' go' : yellow ? ' caution' : '');
    $('status' + p).textContent = green ? `GO - ${d.remaining}s` : yellow ? 'CLEARING' : 'STOP';
    if (green) open.push(names[p]);
  });
  $('sceneStatus').textContent = open.length ? `${open[0].toUpperCase()} MOVING · OTHER ROADS STOP` : d.stage === 'yellow' ? 'YELLOW · PREPARE TO STOP' : 'ALL RED · CLEARING JUNCTION';
  const dqnOption = $('controller').querySelector('option[value="dqn"]');
  if (dqnOption) dqnOption.disabled = !d.dqn_available;
}

function render(now) {
  const r = resize(canvas, ctx), w = r.width, h = r.height, span = Number($('zoom').value), day = $('theme').value === 'day', scale = Math.min(w, h) / span;
  ctx.fillStyle = day ? '#b8c9b8' : '#10252d';
  ctx.fillRect(0, 0, w, h);
  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.scale(scale, -scale);
  ctx.translate(-250, -250);

  // Background Scenery
  for (let x = 10; x < 500; x += 26) {
    for (let y = 10; y < 500; y += 26) {
      if (Math.abs(x - 250) < 27 || Math.abs(y - 250) < 27) continue;
      const seed = (x * 13 + y * 7) % 19;
      if (seed < 4) {
        rect(x, y, 19, 18, day ? '#85ad83' : '#183f37');
        rect(x + 8, y, 1, 18, '#456057');
        rect(x, y + 8, 19, 1, '#456057');
        for (const [tx, ty] of [[4, 4], [14, 4], [4, 14], [14, 14]]) {
          ctx.fillStyle = day ? '#548756' : '#285c48';
          ctx.beginPath();
          ctx.arc(x + tx, y + ty, 2.8, 0, 7);
          ctx.fill();
        }
      } else {
        const bw = seed % 2 ? 18 : 15, bh = seed % 3 ? 17 : 20;
        rect(x + 2, y - 2, bw, bh, day ? '#778d82' : '#071922');
        rect(x, y, bw, bh, day ? (seed % 2 ? '#c8d5cd' : '#d4d7c6') : (seed % 2 ? '#29434f' : '#314b57'));
      }
    }
  }

  // Roads
  rect(238, 0, 24, 500, day ? '#d6dbcd' : '#627777');
  rect(0, 238, 500, 24, day ? '#d6dbcd' : '#627777');
  rect(243.6, 0, 12.8, 500, (day ? '#627375' : '#233740'));
  rect(0, 243.6, 500, 12.8, (day ? '#627375' : '#233740'));
  rect(239.6, 239.6, 20.8, 20.8, day ? '#657779' : '#293e48');
  drawPriorityCorridor();

  // Traffic Markings
  ctx.lineWidth = 0.22;
  ctx.strokeStyle = '#b5b4a0';
  ctx.setLineDash([]);
  for (const s of [-0.3, 0.3]) {
    ctx.beginPath();
    ctx.moveTo(250 + s, 0); ctx.lineTo(250 + s, 237);
    ctx.moveTo(250 + s, 263); ctx.lineTo(250 + s, 500);
    ctx.moveTo(0, 250 + s); ctx.lineTo(237, 250 + s);
    ctx.moveTo(263, 250 + s); ctx.lineTo(500, 250 + s);
    ctx.stroke();
  }

  // Moving Vehicles
  if (state) {
    const signal = state.signal || '', lights = [[242, 262, 0], [262, 258, 4], [258, 238, 8], [238, 242, 12]];
    lights.forEach(([x, y, i]) => {
      const c = signal[i]?.toLowerCase(), color = c === 'g' ? '#8affbc' : c === 'y' ? '#ffc56a' : '#f27676';
      rect(x, y, 1.2, 1.2, color);
    });

    const mix = state.status === 'paused' ? 1 : Math.min(1, (now - receivedAt) / blendDuration);
    for (const [id, v] of positions) {
      const old = previous.get(id) || v;
      let angle = ((v.angle - old.angle + 540) % 360) - 180;
      ctx.save();
      ctx.translate(old.x + (v.x - old.x) * mix, old.y + (v.y - old.y) * mix);
      ctx.rotate(-(old.angle + angle * mix) * Math.PI / 180);

      const color = v.emergency ? '#f4f5e8' : v.vclass === 'bus' || v.vclass === 'truck' ? '#dfb36e' : ['#a9cbd9', '#c5d2cf', '#88b3bd', '#789eac'][id.charCodeAt(id.length - 1) % 4];
      rect(-v.width / 2 + 0.2, -v.length / 2 - 0.3, v.width, v.length, '#071116');
      rect(-v.width / 2, -v.length / 2, v.width, v.length, color);

      if (v.emergency) {
        ctx.shadowBlur = 12;
        ctx.shadowColor = now % 500 < 250 ? '#ff6058' : '#71baff';
        rect(-v.width / 2, 0, v.width, 0.6, ctx.shadowColor);
        ctx.shadowBlur = 0;
      }
      ctx.restore();
    }
  }

  ctx.restore();
  drawRoadLabels(w, h, scale);
  requestAnimationFrame(render);
}

poll();
requestAnimationFrame(render);

// Periodically fetch Benchmark and Defense logs
async function fetchDefenseLogs() {
  try {
    const res = await fetch('/api/logs', { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    if (data.logs && data.logs.length) {
      const rows = data.logs.slice(-10).reverse().map(l => `
        <tr>
          <td>${l.sim_time}s</td>
          <td><span style="color:${l.active_rule.includes('EMERGENCY') ? '#ff7977' : l.active_rule.includes('SOUTH') ? '#ffd084' : '#a5f3ce'}">${l.active_rule}</span></td>
          <td><b>${l.phase}</b></td>
          <td>${l.duration}s</td>
          <td>${l.avg_queue} veh</td>
          <td>${l.throughput}</td>
        </tr>
      `).join('');
      $('auditRows').innerHTML = rows;
    }
  } catch (err) {}
}
setInterval(fetchDefenseLogs, 3000);

async function benchmark() {
  try {
    const response = await fetch('/api/evaluation', { cache: 'no-store' });
    if (!response.ok) return;
    const data = await response.json();
    if (data.status !== 'evaluated') return;
    const labels = {
      fixed_time: 'Fixed cycle',
      actuated: 'Density adaptive',
      dqn: 'Trained DQN',
      vision_actuated: 'Vision AI 3-Tier Priority'
    };
    $('benchmarkRows').replaceChildren(...data.results.map(r => {
      const row = document.createElement('tr');
      for (const value of [
        labels[r.controller] || r.controller,
        r.avg_queue_length_vehicles + ' veh',
        r.avg_wait_time_s + ' s',
        r.avg_throughput_vehicles,
        r.total_collision_vehicle_events + ' / ' + r.total_teleported_vehicles
      ]) {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
      }
      return row;
    }));
  } catch (error) {}
}
benchmark();
setInterval(benchmark, 15000);

window.addEventListener('resize', drawHistory);


// Initialize view mode on page load
if (viewMode) {
  viewMode.onchange();
}


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
        const resp = await fetch('/api/vision/upload_frame', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: b64 })
        });
        const resData = await resp.json();
        if (resData.annotated_jpeg) {
          cameraFeed.src = resData.annotated_jpeg;
        }
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
