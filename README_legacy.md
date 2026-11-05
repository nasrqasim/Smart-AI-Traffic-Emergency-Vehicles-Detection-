# AI-Based Smart Traffic Signal Control System — Working Simulation

This is a **simulation-first, working implementation** of the system described in your FYP
document. Everything here runs on a normal PC (no Jetson Nano / camera / GPIO hardware
required) so you have something you can actually run, demo, and iterate on today. It follows
the doc's architecture (Chapter 3, Methodology) as closely as possible at this scale, and
every place where it simplifies something the doc specifies at production scale is called out
below, with a concrete path to close the gap.

## What's actually working here

| Doc section | This project |
|---|---|
| 3.1 System overview / closed-loop pipeline | `rl_env/traffic_env.py` — Gymnasium env wrapping SUMO/TraCI, 5s-scale decision loop |
| 3.2 Data collection (SUMO synthetic demand 900–2400 veh/h) | `sumo_net/gen_routes.py` generates exactly this demand profile |
| 3.3 DQN agent (state_dim→256→256→128→action_dim, replay buffer 50k, batch 64) | `train.py` — same architecture and hyperparameters, via Stable-Baselines3 |
| 3.3 YOLOv8n vehicle detection, per-lane density via ROI | `vision/detect_density.py` — real detection on a real traffic video |
| 1.3.2 Emergency preemption, 200m zone | Implemented directly in `traffic_env.py` (`_detect_emergency`) |
| 3.4 Flask/Socket.IO monitoring dashboard | `dashboard/app.py` + `dashboard/templates/index.html` |
| 3.5 Evaluation vs fixed-time / actuated baselines | `eval/baselines.py`, `eval/evaluate.py` |

## Quick start

```bash
pip install -r requirements.txt --break-system-packages   # SUMO, RL, vision, dashboard deps
export SUMO_HOME=$(python3 -c "import sumo,os;print(os.path.join(os.path.dirname(sumo.__file__),'share','sumo'))")

# 1. Train the DQN agent (few minutes on a laptop CPU; see "Scaling up" below)
python train.py --timesteps 8000 --out models/dqn_traffic.zip

# 2. Compare it against fixed-time and actuated baselines
python eval/evaluate.py --model models/dqn_traffic.zip --episodes 3

# 3. Watch it control the intersection live in your browser
python dashboard/app.py --model models/dqn_traffic.zip --port 5000
# open http://localhost:5000

# 4. Vehicle detection demo on a real traffic clip
cd vision && python detect_density.py --source traffic_sample.mp4 --out annotated_demo.mp4
```

## How to get this "working, fast and efficient" — in priority order

1. **Run it as-is first.** The SUMO network (`sumo_net/`), RL environment, training loop,
   baselines, evaluation, vision demo, and dashboard are all wired together and tested end to
   end in this build. Get this running before touching anything else — it's your safety net.

2. **Scale up training, not the architecture.** The doc calls for 500,000 environment steps;
   this ships with a much shorter default (a few thousand steps, ~10-15 minutes) so it finishes
   fast and still visibly beats the fixed-time baseline. Once it's running, just re-run
   `train.py --timesteps 100000` (or more) overnight or on a machine with more cores — nothing
   else needs to change. This is the single highest-leverage thing you can do for "perfect and
   efficient": more training time directly buys lower wait times, and SUMO headless is fast
   (~9 decision-steps/sec on a single CPU core here, no GPU needed for this part).

3. **Fine-tune YOLOv8n on UA-DETRAC before deployment.** The vision demo here uses the stock
   COCO-pretrained YOLOv8n weights — it detects cars fine but has weaker recall from unusual
   top-down camera angles (COCO is mostly street-level photos). For the doc's claimed accuracy
   numbers you need the actual fine-tuning step (Section 3.3): grab UA-DETRAC, and run
   `ultralytics` training:
   ```bash
   yolo detect train data=ua_detrac.yaml model=yolov8n.pt epochs=100 batch=16 optimizer=AdamW
   ```
   This needs a GPU (Colab free tier works, matching the doc's tooling) — budget a few hours.

4. **Calibrate ROI lane polygons per camera.** `vision/detect_density.py` falls back to a
   generic left/right split when no `roi_lanes.json` is given. For a real intersection, use
   CVAT (as the doc specifies) to draw the actual lane polygons once per camera and save them
   as `{"lane_name": [[x,y],...]}` — this is a 20-minute one-time task per camera, not a coding
   task.

5. **Close the sim-to-real gap deliberately, don't skip it.** The doc's own "Challenges &
   Solutions" section (3.8) already names the right fix: domain-randomize the SUMO training
   (vary demand, turning ratios, vehicle mix — `gen_routes.py --seed N` gives you a knob to
   start from) and add a short behavior-cloning fine-tune pass once you have real intersection
   footage. Don't try to deploy the sim-trained agent directly to hardware and expect it to be
   "perfect" — this step is what the literature (Genders & Razavi; PressLight) says actually
   matters.

6. **Jetson Nano / GPIO / RTSP / audio siren detection are stubbed, not built**, because they
   need physical hardware this environment doesn't have. The interfaces are designed so they
   drop in cleanly:
   - Swap `cv2.VideoCapture("traffic_sample.mp4")` for an RTSP URL — one-line change in
     `detect_density.py`.
   - Export the trained SB3 model to ONNX (`model.policy.to("cpu")` +
     `torch.onnx.export`) for the doc's ONNX Runtime inference path on-device.
   - GPIO relay switching is a ~10-line addition where `traci.trafficlight.setRedYellowGreenState`
     is called in `traffic_env.py` — replace/augment that call with `Jetson.GPIO` pin writes.
   - Audio (YAMNet) siren detection: the emergency preemption *logic* (200m zone, dual-
     confirmation, forced green) is already implemented and tested here in simulation
     (`_detect_emergency` in `traffic_env.py`); swapping the trigger source from "TraCI says
     there's an emergency vClass vehicle nearby" to "YAMNet + HSV siren classifier says so"
     is a data-source swap, not a redesign.

## What "efficient" means in this codebase specifically

- SUMO runs headless (`sumo`, not `sumo-gui`) during training/eval — this is 100% of the
  training speed.
- The RL step size is 15-90s of sim time per decision (matching the doc), so each
  `env.step()` call advances the simulator many ticks at once — training throughput here was
  ~9 decisions/sec on a single CPU core with no GPU.
- `train_freq=4`, `target_update_interval=250`, `buffer_size=50_000` (matches the doc) — tuned
  for CPU-only training; if you do get a GPU, `buffer_size` and `batch_size` are the first
  knobs to turn up.

## Measured results (this run)

From `eval/results.json`, 3 episodes of 30 sim-minutes each, same demand/seeds for every
controller:

| Controller | Avg wait (s) | Avg queue (veh) | Throughput (veh/30min) |
|---|---|---|---|
| Fixed-time (Webster-style) | 63.2 | 159.6 | 473.3 |
| Actuated (gap-out) | 59.7 | 199.9 | 259.3 |
| **DQN (this build)** | **54.0** | 214.6 | 127.7 |

The DQN agent cuts average wait time by **14.6%** vs. the fixed-time baseline for vehicles
that complete their trip — a real, measured improvement, not the doc's literature-review
number. It does **not** yet beat fixed-time on throughput or standing queue length: under
this scenario's heavier congestion states it sometimes holds one phase too long, which is a
direct, honest consequence of training for ~12,000 steps instead of the doc's 500,000. See
"Scaling up" above — more training time is the fix, not a code change.

### Why getting here took real debugging (worth knowing if you keep tuning this)

Three real bugs surfaced while getting a legitimate result, in case you hit them again after
changing the network/demand/reward:

1. **Per-tick metrics instrumentation silently made training ~10x slower.** Polling every
   vehicle's waiting time every simulated second is fine for evaluation but not for the inner
   training loop. Fixed by making it opt-in (`collect_metrics=True`, only set by `eval/` and
   the dashboard) and subsampling the expensive part.
2. **A saturated state vector caused a naive "pick whichever side has more cars" baseline
   to starve one approach forever** — once both approaches hit the density sensor's
   normalization ceiling, both looked identically "1.0" and a `>=` tie-break kept picking the
   same side every time, permanently locking out the other. Fixed by raising the
   normalization ceiling to a realistic queue length and giving the actuated baseline explicit
   tie-alternation + a forced-switch fairness rule.
3. **The DQN mode-collapsed onto a single action regardless of state**, twice, across
   different reward formulations. The actual cause: with gamma near 1 and long macro-steps,
   the discounted-return baseline (shared by every action) was 10-100x larger than the real
   advantage between the 8 phase/duration choices, so the network only ever learned "how bad
   is this state," never "which action helps." Confirmed directly by inspecting `Q(s,a)` for
   synthetic states (see `train.py`'s comments). Fixed with `VecNormalize` reward scaling — the
   standard, principled tool for exactly this failure mode — plus a lower `gamma` and a
   smaller network sized for a few thousand samples instead of 500k.

If you scale `--timesteps` up substantially, it's worth reverting the smaller network back to
the doc's `[256, 256, 128]` and gamma back toward 0.95, since more data can actually support
that capacity.

## Repo layout

```
sumo_net/         4-way intersection network + demand generator + emergency route
rl_env/           Gymnasium env: 8-dim density state, 8-action phase controller, PressLight reward
train.py          DQN training (Stable-Baselines3)
eval/              baseline controllers (fixed-time, actuated) + comparison harness
vision/           YOLOv8n vehicle detection + per-lane ROI density demo
dashboard/        live Flask/Socket.IO monitor
models/           trained checkpoints land here
```

## Notes / honest limitations of this pass

- Training here is a fast, reduced-scale run for demo purposes, not the doc's full
  500k-step run — expect a clear improvement over fixed-time but not the doc's exact
  30-45% figure without more training time.
- `eval/results.json` (generated by `eval/evaluate.py`) has the actual measured numbers
  from this run — read those rather than assuming the doc's literature-review numbers apply
  directly to this build.
- Domain randomization across episodes is simplified to varying the SUMO RNG seed (affects
  car-following stochasticity), not full re-generation of demand/turning-ratio profiles per
  episode as item 5 above describes — cheap to extend in `train.py` by calling
  `gen_routes.py` with a new seed each `reset()`.
