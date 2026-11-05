# Smart Traffic Signal FYP – Simulation & Real-Time Vision Mode

A local SUMO simulation with live Canvas digital twin, vehicle injection, real-time YOLOv8 computer vision detection, emergency preemption, and four separate approach signals.
**Only one approach is green at a time.** Green changes always pass through 3 seconds of yellow and 2 seconds of all red.

## Run on Windows

Use the project environment:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_simulation.ps1
```

Open http://127.0.0.1:5000. If PowerShell script execution is restricted:

```powershell
.\venv\Scripts\python.exe dashboard/app.py --port 5000
```

SUMO is discovered automatically from the project Python environment. No manual SUMO_HOME setting is needed.
The local server binds to 127.0.0.1. Pause, reset, playback speed, controller choice, and vehicle injection operate on the actual SUMO simulation.

## Computer Vision & 3-Tier Priority Control Hierarchy

The system integrates a real-time computer vision module and a 3-tier intelligent priority rule engine:

1. **Perception & Detection (`vision/camera_stream.py`)**:
   - Supports live webcam (`0`), video footage (`vision/traffic_sample.mp4`), and RTSP/HTTP camera streams.
   - Detects multi-class vehicles (cars, buses, trucks, motorcycles) and identifies emergency vehicles (ambulances, fire engines) using YOLOv8 (`vision/yolov8n.pt`).
   - Maps intersection zones using 4 distinct polygon ROIs (`vision/roi_4way.json`) for North, East, South, and West approaches.
   - Streams live annotated video frames via MJPEG (`/api/video_feed`) directly into the dashboard.

2. **3-Tier Intelligent Priority Hierarchy (`eval/vision_actuated_policy.py`)**:
   - **Rule 1: Emergency Vehicle Preemption (Highest Priority / Safety Critical):**
     Immediately preempts active greens upon detecting an emergency vehicle (ambulance), executes safe clearance (3s yellow + 2s all-red), and grants uninterrupted green corridor passage.
   - **Rule 2: Density-Based Dynamic Extension (Peak Hour / Congestion Management):**
     Continuously monitors vehicle queues. If a specific approach—**specifically the South line**—accumulates high congestion, it bypasses standard timers to extend green dynamically until cleared (with South priority multiplier).
   - **Rule 3: Traditional Fallback Cycle (Low Traffic / Night Mode):**
     When intersection traffic is low or empty, signals revert predictably to a classic fixed cycle rotating every **60 seconds** per approach (N -> E -> S -> W).

3. **Performance Tracking & FYP Defense Reporting (`eval/defense_logger.py`)**:
   - Real-time decision audit trail logging queues, throughput, wait times, emergency preemption events, and dynamic extensions.
   - Downloadable CSV defense report via `/api/export_logs` or the dashboard's "Export Defense Report" button.

## Signal logic

- Separate North, East, South, and West phases. All other roads remain red.
- Density adaptive mode uses vehicle demand and waiting age. Fixed mode cycles N -> E -> S -> W with 20-second greens.
- In automatic modes, each road can receive 10, 20, 30, or 45 seconds of green. A waiting opposing road prevents repeated extensions beyond 45 seconds.
- A waiting road with at least 90 seconds of red receives priority at the next decision. This is a priority threshold, not a guaranteed maximum red time, because other waiting roads and clearance may intervene.
- In automatic modes, emergency vehicles are checked every simulated second within 200 m. Priority preserves yellow and all-red clearance. Concurrent emergencies are ordered by distance.
- New vehicle requests go through a thread-safe queue. Only the simulation thread accesses TraCI.
- Episode time limits are exact. Metrics include completed throughput, time-averaged incoming queue, unfinished/pending vehicles, collision vehicle events, and teleports.

## AI model and reproducibility

The four-approach DQN has 18 inputs (eight lane densities, four phase indicators, elapsed green, emergency presence, and four red ages) and 16 actions.
The final training output is `models/dqn_approach_v3.zip`. Checkpoint selection writes `models/dqn_approach_best.zip`, which the dashboard prefers when present.

```powershell
# In-process SUMO is much faster for training; keep the dashboard in its own process.
$env:TRAFFIC_USE_LIBSUMO = '1'
.\venv\Scripts\python.exe -u train.py --timesteps 100000 --episode-seconds 1800 --randomize-routes --out models/dqn_approach_v3.zip

# Select a checkpoint on validation seeds before touching test seeds
.\venv\Scripts\python.exe eval/select_model.py --episodes 3 --seed 9000

# Held-out scenarios, same demand and seeds for all three controllers
.\venv\Scripts\python.exe eval/evaluate.py --model models/dqn_approach_best.zip --episodes 10 --episode-seconds 1800 --seed 10000 --randomize-routes --out eval/held_out_results_v3.json

# Start a new terminal to run the dashboard
.\run_simulation.ps1 -Controller vision_actuated
```

## Colab / VS Code

```powershell
.\venv\Scripts\python.exe prepare_colab.py
```

Open `notebooks/Traffic_Training_Colab.ipynb` and connect your VS Code Colab extension to a runtime. Run the cells in order.
Upload `notebooks/traffic_training.zip` when requested. The notebook installs dependencies, supports Google Drive checkpoint storage, trains DQN, evaluates held-out scenarios, and exports the model.

## Accuracy and vision

Traffic control is evaluated through queues, throughput, delay and safety outcomes, rather than a classification accuracy percentage.
The simulation integrates exact SUMO state alongside real-time YOLOv8 video detection.
`vision/yolov8n.pt` is a pretrained detector. The notebook provides optional detector training and independent test evaluation after you supply a dataset YAML.

## Verify

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
node --check dashboard/static/app.js
```

Generate a shareable report and chart from measured results:

```powershell
.\venv\Scripts\python.exe eval/render_report.py
```
