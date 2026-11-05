"""Local dashboard for the exclusive four-approach SUMO simulation.

Runs one simulator owner thread, live camera vision processor, and exposes
live measurements, video stream, and queued controls.
"""
import argparse
import os
import queue
import sys
import threading
import time
import json
import logging

from flask import Flask, render_template, jsonify, request, Response
try:
    from flask_socketio import SocketIO
except ImportError:
    class DummySocketIO:
        def __init__(self, *args, **kwargs): pass
        def on(self, *args, **kwargs):
            return lambda fn: fn
        def emit(self, *args, **kwargs): pass
        def run(self, app, **kwargs):
            app.run(host=kwargs.get('host', '127.0.0.1'), port=kwargs.get('port', 5000), threaded=True)
    SocketIO = DummySocketIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rl_env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "eval"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vision"))

from traffic_env import TrafficSignalEnv, INCOMING_LANES, SPAWN_TYPE_MAP  # noqa: E402
from baselines import ApproachAdaptivePolicy, ApproachFixedPolicy, DQNPolicy, VisionActuatedPriorityPolicy  # noqa: E402
from camera_stream import camera_processor  # noqa: E402
from defense_logger import defense_logger  # noqa: E402

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
app.config["SECRET_KEY"] = "ai-stscs-demo"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

LANE_LABELS = ["N-in", "N-left", "S-in", "S-left", "E-in", "E-left", "W-in", "W-left"]

_state_lock = threading.Lock()
_running = True

# Spawn requests from the browser's road buttons. Only the simulation_loop
# thread ever touches `traci`, so requests are handed off here and drained
# inside TrafficSignalEnv._tick() rather than called directly from the
# Socket.IO request-handler thread.
spawn_queue = queue.Queue()

# Reset is checked every simulated second by the simulator owner thread.
_force_reset = threading.Event()
_paused = threading.Event()
_speed = 0.5
_controller = "vision_actuated"
_latest = {"status": "starting"}
_dqn_available = False
_active_controller = "vision_actuated"
_current_active_rule = "TRADITIONAL_FALLBACK_60S"


@app.get("/api/state")
def state():
    with _state_lock:
        result = dict(_latest)
    if result.get("status") in ("running", "paused"):
        result["status"] = "paused" if _paused.is_set() else "running"
    return jsonify(result)


@app.get("/api/evaluation")
def evaluation():
    path = os.path.join(os.path.dirname(__file__), "..", "eval", "held_out_results_v3.json")
    if not os.path.isfile(path):
        return jsonify(status="pending", results=[])
    with open(path, encoding="utf-8") as file:
        return jsonify(status="evaluated", results=json.load(file))


@app.get("/api/video_feed")
def video_feed():
    """Streams real-time YOLOv8-annotated video frames from the intersection camera."""
    def generate():
        while _running:
            frame = camera_processor.get_latest_jpeg()
            if frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.04)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.post("/api/vision/upload_frame")
def upload_browser_frame():
    """Receives a real-time frame from the user's laptop camera/webcam via browser navigator.mediaDevices."""
    import base64
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image")
    if not image_b64:
        return jsonify(error="No image provided"), 400
    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        raw_bytes = base64.b64decode(image_b64)
        res = camera_processor.process_browser_frame(raw_bytes)
        return jsonify(res)
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.get("/api/vision/status")
def vision_status():
    return jsonify(camera_processor.get_telemetry())


@app.post("/api/vision/trigger_emergency")
def vision_trigger_emergency():
    data = request.get_json(silent=True) or {}
    approach = data.get("approach", "S")
    vtype = data.get("vehicle_type", "ambulance")
    camera_processor.trigger_emergency_test(approach, vtype)
    if spawn_queue.qsize() < 100:
        spawn_queue.put(dict(road=approach, vehicle_type=vtype))
    return jsonify(ok=True, message=f"Emergency {vtype} triggered on approach {approach}")


@app.post("/api/vision/clear_emergency")
def vision_clear_emergency():
    camera_processor.clear_emergency_test()
    return jsonify(ok=True)


@app.post("/api/vision/source")
def vision_set_source():
    data = request.get_json(silent=True) or {}
    src = data.get("source")
    if src is not None:
        camera_processor.set_source(src)
        return jsonify(ok=True, source=src)
    return jsonify(error="Missing source"), 400


@app.get("/api/logs")
def get_defense_logs():
    return jsonify({
        "summary": defense_logger.get_summary(),
        "logs": defense_logger.get_recent_logs(limit=50)
    })


@app.get("/api/export_logs")
def export_defense_logs():
    path = defense_logger.export_csv()
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=traffic_defense_report.csv"}
    )


@app.post("/api/control")
def control():
    global _speed, _controller
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify(error="Expected a JSON object"), 400
    if "paused" in data and not isinstance(data["paused"], bool):
        return jsonify(error="paused must be true or false"), 400
    if "controller" in data and data["controller"] not in ("actuated", "fixed_time", "dqn", "vision_actuated"):
        return jsonify(error="Unknown controller"), 400
    if data.get("controller") == "dqn" and not _dqn_available:
        return jsonify(error="A compatible DQN checkpoint is required"), 409
    if "road" in data and (data["road"] not in ("N", "S", "E", "W") or data.get("vehicle_type") not in SPAWN_TYPE_MAP):
        return jsonify(error="Invalid vehicle request"), 400
    if "speed" in data:
        try:
            value = float(data["speed"])
            if value not in (0.25, 0.5, 1, 2, 5, 10, 20):
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify(error="Choose a supported playback speed"), 400
        _speed = value
    if "paused" in data:
        _paused.set() if data["paused"] else _paused.clear()
    if "controller" in data:
        _controller = data["controller"]
    if data.get("reset"):
        _force_reset.set()
    if "road" in data:
        if spawn_queue.qsize() >= 100:
            return jsonify(error="Vehicle insertion queue is full"), 429
        spawn_queue.put(dict(road=data["road"], vehicle_type=data["vehicle_type"]))
    return jsonify(ok=True)


@socketio.on("spawn_vehicle")
def handle_spawn_vehicle(data):
    if not isinstance(data, dict):
        return
    if data.get("road") not in ("N", "S", "E", "W"):
        return
    if data.get("vehicle_type") not in SPAWN_TYPE_MAP:
        return
    if spawn_queue.qsize() < 100:
        spawn_queue.put(data)


@socketio.on("reset_simulation")
def handle_reset_simulation(_data=None):
    _force_reset.set()


def simulation_loop(policy, episode_seconds, seed, sumocfg):
    global _running, _latest, _active_controller, _current_active_rule
    from traffic_env import traci
    vision_policy = VisionActuatedPriorityPolicy()
    policies = {
        "actuated": ApproachAdaptivePolicy(),
        "fixed_time": ApproachFixedPolicy(),
        "vision_actuated": vision_policy
    }
    if policy is not None:
        policies["dqn"] = policy

    while _running:
        env = TrafficSignalEnv(max_steps=episode_seconds, seed=seed, collect_metrics=True,
                               sumocfg=sumocfg, augmented_state=True, single_approach=True)
        env.attach_spawn_queue(spawn_queue)
        env.stop_requested = _force_reset.is_set

        def tick(st):
            global _latest
            metrics = env.get_episode_metrics()
            obs = env._get_state()
            cam_telemetry = camera_processor.get_telemetry()
            payload = dict(
                metrics,
                status="paused" if _paused.is_set() else "running",
                sim_time=st,
                phase=env._last_phase,
                stage=env._signal_stage,
                remaining=env._remaining,
                speed=_speed,
                controller=_active_controller,
                requested_controller=_controller,
                next_phase=env._next_phase,
                dqn_available=_dqn_available,
                red_age=dict(env._red_age),
                signal=traci.trafficlight.getRedYellowGreenState("center"),
                emergency_preemption=(env._detect_emergency() is not None or cam_telemetry["emergency"]["detected"]),
                active_rule=_current_active_rule,
                camera_telemetry=cam_telemetry,
                vehicles=env.get_vehicle_snapshot(),
                density={LANE_LABELS[i]: float(obs[i]) for i in range(8)}
            )
            with _state_lock:
                _latest = payload
            socketio.emit("vehicle_tick", payload)
            while _paused.is_set() and not _force_reset.is_set() and _running:
                time.sleep(0.05)
            env.playback_delay = 1.0 / _speed

        env.set_tick_callback(tick)
        obs, _ = env.reset()
        for controller in policies.values():
            controller.reset()
        defense_logger.reset()
        terminated = truncated = False

        while not (terminated or truncated) and _running:
            if _force_reset.is_set():
                _force_reset.clear()
                break
            _active_controller = _controller
            active_pol = policies.get(_active_controller, vision_policy)

            if _active_controller == "vision_actuated":
                cam_data = camera_processor.get_telemetry()
                action = active_pol.act(obs, camera_data=cam_data)
                _current_active_rule = active_pol.active_rule
                camera_processor.update_active_rule(_current_active_rule)
            else:
                action = active_pol.act(obs)
                _current_active_rule = getattr(active_pol, "active_rule", "DENSITY_ACTUATED" if _active_controller == "actuated" else "FIXED_CYCLE")
                camera_processor.update_active_rule(_current_active_rule)

            obs, reward, terminated, truncated, info = env.step(action)
            metrics = env.get_episode_metrics()

            density_map = {LANE_LABELS[i]: float(obs[i]) for i in range(8)}
            defense_logger.log_decision(
                sim_time=info["sim_time"],
                controller=_active_controller,
                active_rule=_current_active_rule,
                phase=info["phase"],
                duration=info["duration"],
                density_dict=density_map,
                metrics=metrics,
                camera_counts=camera_processor.counts
            )

            payload = {
                "sim_time": info["sim_time"],
                "phase": info["phase"],
                "duration": info["duration"],
                "emergency_preemption": info["emergency_preemption"],
                "active_rule": _current_active_rule,
                "density": density_map,
                "avg_queue_length": round(metrics["avg_queue_length"], 2),
                "avg_wait_time_s": round(metrics["avg_wait_time_s"], 2),
                "throughput_vehicles": metrics["throughput_vehicles"],
                "reward": round(float(reward), 1),
            }
            socketio.emit("sim_update", payload)

        env.close()
        seed += 1  # vary the scenario slightly each loop


@app.route("/")
def index():
    return render_template("index.html")


@app.after_request
def development_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def main():
    ap = argparse.ArgumentParser()
    default_model = os.path.join(os.path.dirname(__file__), "..", "models", "dqn_approach_best.zip")
    if not os.path.isfile(default_model):
        default_model = os.path.join(os.path.dirname(__file__), "..", "models", "dqn_approach_v3.zip")
    ap.add_argument("--model", default=default_model)
    ap.add_argument("--episode-seconds", type=int, default=1800)
    ap.add_argument("--seed", type=int, default=500)
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--controller", choices=["vision_actuated", "actuated", "fixed_time", "dqn"], default="vision_actuated")
    ap.add_argument("--video-source", default=None, help="Video file path, webcam index 0, or RTSP URL")
    ap.add_argument("--sumocfg", default=os.path.join(
        os.path.dirname(__file__), "..", "sumo_net", "intersection_dashboard.sumocfg"),
        help="Automatic traffic scenario for the live demo")
    args = ap.parse_args()

    global _controller, _dqn_available
    _controller = args.controller

    if args.video_source:
        camera_processor.set_source(args.video_source)

    # Start computer vision processor in background
    camera_processor.start()

    if os.path.exists(args.model):
        print(f"Loading DQN policy from {args.model}")
        try:
            policy = DQNPolicy(args.model)
            if policy.model.observation_space.shape == (18,) and policy.model.action_space.n == 16:
                _dqn_available = True
            else:
                print("Model shape mismatch, keeping vision/adaptive policies available.")
                policy = None
        except Exception as e:
            print(f"Could not load DQN model ({e}), using Vision/Adaptive policies.")
            policy = None
    else:
        print("DQN model checkpoint not found; Vision-Actuated priority controller is active.")
        policy = None
        if _controller == "dqn":
            _controller = "vision_actuated"

    def guarded_loop(*params):
        global _latest
        try:
            simulation_loop(*params)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            with _state_lock:
                _latest = {"status": "error", "error": str(exc)}

    t = threading.Thread(
        target=guarded_loop,
        args=(policy, args.episode_seconds, args.seed, args.sumocfg),
        daemon=True,
    )
    t.start()

    print(f"Starting Smart Traffic Dashboard on http://{args.host}:{args.port}")
    socketio.run(app, host=args.host, port=args.port, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
