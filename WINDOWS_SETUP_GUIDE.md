# Running This Project on a Fresh Windows PC

This guide walks through everything needed to get this project running from
the shared zip folder on a Windows machine, including the Windows-specific
fixes already applied to the code (so you should **not** hit the errors
described in the Troubleshooting section below — they're documented here in
case you ever revert those files or move to a different machine/SUMO version).

## 1. Prerequisites

- **Windows 10 or 11**
- **Python 3.10 or newer** (this was built and tested against **3.12.10**).
  Check with:
  ```powershell
  python --version
  ```
  If this fails or shows an older version, install Python from
  [python.org](https://www.python.org/downloads/) first.

## 2. Unzip and locate the project root

Extract the zip. Note: the shared archive may contain a nested folder of the
same name (e.g. `AI_Smart_Traffic_Signal_FYP\AI_Smart_Traffic_Signal_FYP\`) —
that inner folder is the actual project root containing `README.md`,
`requirements.txt`, `train.py`, etc. Open a PowerShell terminal there.

## 3. Create a virtual environment and install dependencies

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

This installs SUMO, `stable-baselines3`, `torch`, `ultralytics` (YOLOv8),
Flask/Socket.IO, etc. It downloads several hundred MB (torch and the SUMO
binaries are the largest) — expect this step to take 5-15 minutes depending
on your connection.

## 4. Set `SUMO_HOME` (every new terminal session)

**Important Windows-specific note:** on this platform, the `eclipse-sumo`
pip package lays out `bin/`, `data/`, and `tools/` **directly inside** the
`sumo` package folder — there is no `share/sumo` subfolder like on Linux.
Use this PowerShell command (not the Linux-style one sometimes shown in
generic SUMO docs):

```powershell
$env:SUMO_HOME = (Resolve-Path ".\venv\Lib\site-packages\sumo").Path
```

You must run this **once per new terminal window** before running anything
that touches SUMO (smoke test, training, evaluation, vision demo, dashboard).
PowerShell environment variables don't persist between separate terminal
sessions.

To sanity-check it's set correctly:
```powershell
Test-Path "$env:SUMO_HOME\bin\sumo.exe"   # should print True
```

## 5. Smoke test (run this first)

Confirms SUMO, the network files, and the RL environment all work together:

```powershell
.\venv\Scripts\python.exe -c "
import sys; sys.path.insert(0, 'rl_env')
from traffic_env import TrafficSignalEnv
env = TrafficSignalEnv(max_steps=100)
obs, info = env.reset()
print('Reset OK, obs shape:', obs.shape)
for i in range(3):
    obs, r, term, trunc, info = env.step(env.action_space.sample())
    print('step', i, 'reward', round(r, 2))
env.close()
print('Smoke test OK')
"
```

You should see `Smoke test OK` at the end with no tracebacks.

## 6. Evaluate the existing trained model

```powershell
.\venv\Scripts\python.exe eval\evaluate.py --model models\dqn_traffic.zip --episodes 3
```

Takes a few minutes (3 episodes × 3 controllers × 30 simulated minutes each).
Prints a fixed-time vs actuated vs DQN comparison table and writes it to
`eval\results.json`.

## 7. Vehicle-detection (YOLOv8) demo

```powershell
cd vision
..\venv\Scripts\python.exe detect_density.py --source traffic_sample.mp4 --frame 200 --out test_frame.jpg
cd ..
```

First run auto-downloads `yolov8n.pt` (~6 MB) from Ultralytics' GitHub
releases — needs an internet connection once.

## 8. Launch the live interactive dashboard

```powershell
.\venv\Scripts\python.exe dashboard\app.py --model models\dqn_traffic.zip --port 5000
```

Open **http://localhost:5000** in a browser. You'll see vehicles animating
live through the intersection, with spawn buttons around each compass edge
(car/bus/truck/moto/ambulance/firetruck). By default this uses a
lighter-traffic scenario (`sumo_net\intersection_dashboard.sumocfg`) tuned
for watchability; pass `--sumocfg sumo_net\intersection.sumocfg` to use the
full-demand scenario that matches `eval\evaluate.py`'s numbers instead.

If the simulation ever looks frozen (an intersection can genuinely gridlock
under this trained model — see the Known Limitations section of the progress
report), click **"🔄 Reset simulation"** in the top-right of the page rather
than restarting the server.

## 9. Training a new model (optional)

```powershell
.\venv\Scripts\python.exe train.py --timesteps 10000 --out models\my_model.zip
```

- `--timesteps`: total environment steps. Real throughput on a typical
  laptop CPU core is roughly **2.5-5 steps/sec** (this varies by machine —
  don't assume the higher figures sometimes quoted for faster hardware).
  10,000 steps takes roughly 30-45 minutes; the FYP doc's full 500,000-step
  spec would take the better part of a day on a single CPU core.
- `--net-arch "256,256,128"` and `--gamma 0.95`: use these together for large
  runs (tens of thousands of steps or more) to match the doc's architecture.
  For anything under ~15,000 steps, leave these at their defaults
  (`64,64` / `0.9`) — the larger network doesn't have enough data to train
  reliably at small scale and tends to collapse onto a single action.
- The script checkpoints every 5,000 steps (configurable via `--save-freq`)
  into `models\checkpoints\`, so a crash or interruption doesn't lose all
  progress. To resume from a checkpoint:
  ```powershell
  .\venv\Scripts\python.exe train.py --timesteps 5000 --resume-from models\checkpoints\my_model_10000_steps.zip --resume-vecnormalize models\checkpoints\my_model_vecnormalize_10000_steps.pkl --out models\my_model.zip
  ```
- **Don't run the live dashboard at the same time as training** — they
  compete for CPU and can slow training to a crawl (observed first-hand:
  one run's throughput collapsed from ~3 steps/sec to effectively 0 while
  the dashboard was also running, and eventually crashed outright — see the
  progress report's error log for details).

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError: [WinError 2]` when resetting the environment | `traffic_env.py` was pointing at a Linux SUMO binary path | Already fixed in this codebase (`_sumo_binary()` resolves from `SUMO_HOME\bin` on Windows). If you see this, confirm you're using the version of `traffic_env.py` from this zip, not an older copy. |
| `SUMO_HOME` guesses a `share\sumo` path that doesn't exist | Following generic (Linux-oriented) SUMO setup instructions | Use the PowerShell command in Step 4 above instead. |
| `Error: tcpip::Socket::accept() ... Address already in use` during training | Transient port collision when SUMO restarts many times in a row (especially under CPU load from another process) | Already mitigated with automatic retry logic in `traffic_env.py`. If it still happens repeatedly, make sure nothing else (like the dashboard) is running SUMO at the same time. |
| Dashboard page loads but no vehicles ever move | `SUMO_HOME` not set in the terminal that launched `dashboard\app.py` | Re-run the Step 4 command in that same terminal before launching the dashboard. |
| Dashboard looks "stuck" / frozen | Genuine simulation gridlock (a real, documented limitation of the current short-trained model, not a rendering bug) | Click "🔄 Reset simulation" in the dashboard UI. |
| `pip install` fails partway through | Interrupted download (torch and the SUMO packages are large) | Re-run the same `pip install -r requirements.txt` command — pip resumes/skips already-installed packages. |
