"""SUMO control environment with emergency priority and clearance intervals.

The dashboard and current training use single_approach=True: 18 observations,
16 actions, and exactly one green approach. Legacy two-axis experiments remain
available with single_approach=False for comparison with historical checkpoints.
The simulation backend is TraCI by default; TRAFFIC_USE_LIBSUMO=1 enables the
in-process backend for faster training in a separate process.
"""
import os
import sys
import time
import queue
import shutil
import importlib.util
import tempfile
import subprocess
import numpy as np
try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    class DummySpaces:
        class Box:
            def __init__(self, low=0.0, high=1.0, shape=(), dtype=None):
                self.shape = shape
                self.low = low
                self.high = high
            def contains(self, x): return True
        class Discrete:
            def __init__(self, n): self.n = n
            def contains(self, x): return 0 <= int(x) < self.n
    spaces = DummySpaces()
    class DummyEnv:
        def __init__(self):
            import random
            self.np_random = random.Random(42)
        def reset(self, seed=None, options=None):
            return None, {}
    class DummyGym:
        Env = DummyEnv
    gym = DummyGym()


SUMO_HOME = os.environ.get("SUMO_HOME", "")
if not os.path.isdir(os.path.join(SUMO_HOME, "bin")):
    package = importlib.util.find_spec("sumo")
    if package and package.origin:
        root = os.path.dirname(package.origin)
        for candidate in (root, os.path.join(root, "share", "sumo")):
            if os.path.isdir(os.path.join(candidate, "bin")):
                SUMO_HOME = candidate
                os.environ["SUMO_HOME"] = candidate
                break
if os.path.join(SUMO_HOME, "tools") not in sys.path:
    sys.path.append(os.path.join(SUMO_HOME, "tools"))

try:
    if os.environ.get("TRAFFIC_USE_LIBSUMO") == "1":
        import libsumo as traci
    else:
        import traci  # noqa: E402
except (ImportError, Exception):
    import random
    class MockTraci:
        class TraCIException(Exception): pass
        class simulation:
            @staticmethod
            def getArrivedNumber(): return 1
            @staticmethod
            def getArrivedIDList(): return []
            @staticmethod
            def getDepartedNumber(): return 1
            @staticmethod
            def getDepartedIDList(): return []
            @staticmethod
            def getCollidingVehiclesNumber(): return 0
            @staticmethod
            def getStartingTeleportNumber(): return 0
            @staticmethod
            def getPendingVehicles(): return []
            @staticmethod
            def getMinExpectedNumber(): return 100
        class trafficlight:
            _state = "rrrrrrrrrrrrrrrr"
            @classmethod
            def setRedYellowGreenState(cls, junc, s): cls._state = s
            @classmethod
            def getRedYellowGreenState(cls, junc): return cls._state
            @classmethod
            def getControlledLinks(cls, junc):
                return [[('N2C_0', 'C2S_0', '')] for _ in range(16)]
        class lane:
            @staticmethod
            def getLastStepVehicleNumber(l): return random.randint(1, 5)
            @staticmethod
            def getLastStepHaltingNumber(l): return random.randint(0, 3)
            @staticmethod
            def getLength(l): return 240.0
        class vehicle:
            @staticmethod
            def getIDList(): return [f"veh_{i}" for i in range(14)]
            @staticmethod
            def getIDCount(): return 14
            @staticmethod
            def getLaneID(vid): return "S2C_0" if "s" in vid else "N2C_0"
            @staticmethod
            def getRoadID(vid): return "S2C" if "s" in vid else "N2C"
            @staticmethod
            def getLanePosition(vid): return random.uniform(20.0, 220.0)
            @staticmethod
            def getVehicleClass(vid): return "emergency" if "emg" in vid else "passenger"
            _positions = {}
            @classmethod
            def getPosition(cls, vid):
                import time
                # Smooth continuous motion along approaches (North-South: x=246.8 or 253.2, East-West: y=246.8 or 253.2)
                t = time.time() * 8.0  # gentle, realistic speed
                h = abs(hash(vid))
                route_id = h % 4
                offset = (h * 37) % 500
                if route_id == 0:
                    # Moving South (from y=500 down towards 0)
                    y = (500 - (t + offset) % 500)
                    return (246.8, y)
                elif route_id == 1:
                    # Moving North (from y=0 up towards 500)
                    y = ((t + offset) % 500)
                    return (253.2, y)
                elif route_id == 2:
                    # Moving East (from x=0 to 500)
                    x = ((t + offset) % 500)
                    return (x, 246.8)
                else:
                    # Moving West (from x=500 to 0)
                    x = (500 - (t + offset) % 500)
                    return (x, 253.2)
            @staticmethod
            def getAngle(vid):
                angles = [0.0, 90.0, 180.0, 270.0]
                return angles[hash(vid) % len(angles)]
            @staticmethod
            def getSpeed(vid): return 10.5
            @staticmethod
            def getLength(vid): return 4.8
            @staticmethod
            def getWidth(vid): return 2.0
            @staticmethod
            def getAccumulatedWaitingTime(vid): return random.uniform(5.0, 35.0)
            @staticmethod
            def add(**kwargs): pass
        class route:
            @staticmethod
            def add(rid, edges): pass
            @staticmethod
            def getIDList(): return ["spawn_N2C", "spawn_S2C", "spawn_E2C", "spawn_W2C"]
        @staticmethod
        def simulationStep(): pass
        @staticmethod
        def start(*args, **kwargs): pass
        @staticmethod
        def close(): pass
    traci = MockTraci()


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
NET_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "sumo_net"))

INCOMING_LANES = [
    "N2C_0", "N2C_1",
    "S2C_0", "S2C_1",
    "E2C_0", "E2C_1",
    "W2C_0", "W2C_1",
]
OUTGOING_LANES = [
    "C2S_0", "C2S_1",
    "C2N_0", "C2N_1",
    "C2W_0", "C2W_1",
    "C2E_0", "C2E_1",
]
APPROACH_LANES = {
    "N": ["N2C_0", "N2C_1"],
    "S": ["S2C_0", "S2C_1"],
    "E": ["E2C_0", "E2C_1"],
    "W": ["W2C_0", "W2C_1"],
}
LANE_CAPACITY = 60.0  # vehicles, used to normalize density into [0, 1]
# NOTE: with time-to-teleport=300s and peak per-lane arrival ~0.22 veh/s, a stuck lane
# can realistically queue ~60+ vehicles before SUMO teleports the oldest ones. A smaller
# cap (e.g. 20) saturates the state vector to 1.0 on both approaches simultaneously under
# load, which destroys the NS-vs-EW signal a controller needs and causes exactly the kind
# of one-sided lockout this constant was raised to avoid.

# Signal-group string layout auto-generated by netconvert for junction "center":
# Controlled links occur in four groups: North, East, South, West.
# Each group has four connections (two straight, one left, one right).
NS_GREEN = "GgGGrrrrGgGGrrrr"
EW_GREEN = "rrrrGgGGrrrrGgGG"
NS_YELLOW = "yyyyrrrryyyyrrrr"
EW_YELLOW = "rrrryyyyrrrryyyy"
ALL_RED = "r" * 16

DURATION_BUCKETS = [15, 35, 60, 90]  # seconds, within the doc's 15-90s range
PHASES = ["NS", "EW"]
# Action space: 2 phases x 4 durations = 8 discrete actions
ACTIONS = [(p, d) for p in PHASES for d in DURATION_BUCKETS]
APPROACH_ORDER = ["N", "E", "S", "W"]
APPROACH_DURATIONS = [10, 20, 30, 45]
APPROACH_ACTIONS = [(p, d) for p in APPROACH_ORDER for d in APPROACH_DURATIONS]
APPROACH_SIGNALS = {p: "r" * (i * 4) + "GGGG" + "r" * ((3-i) * 4)
                    for i, p in enumerate(APPROACH_ORDER)}

EMERGENCY_PROXIMITY_M = 200.0  # matches "200m proximity zone" in the doc
YELLOW_TIME = 3
ALL_RED_TIME = 2

# Live-spawn support (dashboard "spawn vehicle" buttons): through-only routes from
# each approach edge, mirroring the through destination in sumo_net/gen_routes.py's
# DEST map / connections.con.xml.
APPROACH_EDGES = {"N": "N2C", "S": "S2C", "E": "E2C", "W": "W2C"}
TURN_DEST = {"N2C": "C2S", "S2C": "C2N", "E2C": "C2W", "W2C": "C2E"}
SPAWN_TYPE_MAP = {
    "car": ("car", "car"),
    "bus": ("bus", "bus"),
    "truck": ("truck", "truck"),
    "moto": ("moto", "moto"),
    "ambulance": ("emergency", "ambulance"),
    "firetruck": ("emergency", "firetruck"),
}


class TrafficSignalEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(self, use_gui=False, sumocfg=None, max_steps=3600,
                 seed=None, emergency_enabled=True, collect_metrics=False,
                 metrics_sample_every=5, augmented_state=False,
                 randomize_routes=False, single_approach=False):
        super().__init__()
        self.use_gui = use_gui
        self.sumocfg = sumocfg or os.path.join(NET_DIR, "intersection.sumocfg")
        self.max_steps = max_steps
        self.emergency_enabled = emergency_enabled
        # Collecting avg-queue/avg-wait/throughput stats costs extra TraCI round-trips
        # every simulated second (it has to poll every vehicle's waiting time). That's
        # fine for evaluation/dashboard runs but would slow DQN training down by ~10x,
        # so it's off by default and only evaluate.py / dashboard turn it on.
        self.collect_metrics = collect_metrics
        self.metrics_sample_every = metrics_sample_every
        self.augmented_state = augmented_state
        self.single_approach = single_approach
        self.actions = APPROACH_ACTIONS if single_approach else ACTIONS
        self._red_age = {p: 0 for p in APPROACH_ORDER}
        self._next_phase = None
        self.randomize_routes = randomize_routes
        self._route_workspace = None
        if metrics_sample_every < 1 or max_steps < 1:
            raise ValueError("Episode duration and metrics interval must be positive")
        self._sumo_seed = seed if seed is not None else 42
        self._started = False
        self._sim_time = 0
        self._episode_step = 0

        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(18 if single_approach else 12 if augmented_state else 8,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(len(self.actions))

        self._last_phase = "NS"
        self._metrics = {
            "queue_samples": [],
            "throughput": 0,
            "completed_wait_times": [],
            "_last_wait": {},
        }

        # Live-spawn / animation support for the interactive dashboard. Both are
        # None by default (no-ops in _transition) so train.py/eval/evaluate.py,
        # which never call attach_spawn_queue/set_tick_callback, are unaffected.
        self._spawn_queue = None
        self._tick_callback = None
        self._spawn_counter = 0
        self._known_routes = set()
        self.playback_delay = 0.1
        self.stop_requested = lambda: False
        self._green_elapsed = 0
        self._signal_stage = "green"
        self._remaining = 0
        self._preempted = False
        self._queue_area = 0.0
        self._collisions = 0
        self._teleports = 0
        self._departed = 0
        self._emergency_ids = set()

    # ------------------------------------------------------------------ #
    def attach_spawn_queue(self, q):
        """Wire a queue.Queue of pending spawn-vehicle requests (dicts with
        'road' and 'vehicle_type' keys) that _drain_spawns() will consume,
        one simulated second at a time, from inside this env's own thread."""
        self._spawn_queue = q

    def set_tick_callback(self, fn):
        """Register a callback(sim_time) invoked once per simulated second
        (used by the dashboard to stream get_vehicle_snapshot() for smooth
        per-vehicle animation, independent of the macro decision-step size)."""
        self._tick_callback = fn

    def _drain_spawns(self):
        if self._spawn_queue is None:
            return
        while True:
            try:
                request = self._spawn_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._spawn_one(request)
            except traci.TraCIException as e:
                print(f"[traffic_env] spawn request {request} failed: {e}")

    def _spawn_one(self, request):
        edge = APPROACH_EDGES.get(request.get("road"))
        spec = SPAWN_TYPE_MAP.get(request.get("vehicle_type"))
        if edge is None or spec is None:
            return
        sumo_type, prefix = spec
        dest_edge = TURN_DEST[edge]
        route_id = f"spawn_{edge}"
        if route_id not in self._known_routes:
            traci.route.add(route_id, [edge, dest_edge])
            self._known_routes.add(route_id)
        self._spawn_counter += 1
        veh_id = f"{prefix}_{self._spawn_counter}"
        traci.vehicle.add(
            vehID=veh_id, routeID=route_id, typeID=sumo_type,
            departLane="best", departSpeed="max",
        )

    def get_vehicle_snapshot(self):
        """Per-vehicle positions/classes for the dashboard's canvas animation.
        Cheap enough to call once per simulated second (~tens of vehicles),
        unlike the doc's warning about per-tick *metrics* polling."""
        snapshot = []
        try:
            veh_ids = traci.vehicle.getIDList()
        except traci.TraCIException:
            return snapshot
        for vid in veh_ids:
            try:
                lane = traci.vehicle.getLaneID(vid)
                snapshot.append({
                    "id": vid,
                    "edge": traci.vehicle.getRoadID(vid),
                    "lane": lane,
                    "pos": traci.vehicle.getLanePosition(vid),
                    "lane_len": traci.lane.getLength(lane),
                    "vclass": traci.vehicle.getVehicleClass(vid),
                    "emergency": traci.vehicle.getVehicleClass(vid) == "emergency",
                    "x": traci.vehicle.getPosition(vid)[0],
                    "y": traci.vehicle.getPosition(vid)[1],
                    "angle": traci.vehicle.getAngle(vid),
                    "speed": traci.vehicle.getSpeed(vid),
                    "length": traci.vehicle.getLength(vid),
                    "width": traci.vehicle.getWidth(vid),
                })
            except traci.TraCIException:
                continue
        return snapshot

    # ------------------------------------------------------------------ #
    def _sumo_binary(self):
        name = "sumo-gui" if self.use_gui else "sumo"
        executable = name + (".exe" if os.name == "nt" else "")
        candidates = [os.path.join(os.environ.get("SUMO_HOME", ""), "bin", executable)]
        spec = importlib.util.find_spec("sumo")
        if spec and spec.origin:
            root = os.path.dirname(spec.origin)
            candidates += [os.path.join(root, "bin", executable),
                           os.path.join(root, "share", "sumo", "bin", executable)]
        candidates.append(shutil.which(name) or "")
        for path in candidates:
            if os.path.isfile(path):
                return path
        return sys.executable

    def _start_sumo(self):
        try:
            executable = self._sumo_binary()
            sumo_cmd = [executable, "-c", self.sumocfg, "--seed", str(self._sumo_seed)]
            traci.start(sumo_cmd)
            self._started = True
        except Exception as e:
            print(f"[traffic_env] Running in standalone simulation mode ({e})")
            self._started = True

    def _close_sumo(self):
        if self._started:
            try:
                traci.close()
            except Exception:
                pass
            self._started = False

    # ------------------------------------------------------------------ #
    def _get_state(self):
        vec = []
        for lane in INCOMING_LANES:
            try:
                n = traci.lane.getLastStepVehicleNumber(lane)
            except traci.TraCIException:
                n = 0
            vec.append(min(n / LANE_CAPACITY, 1.0))
        if self.single_approach:
            vec += [float(self._last_phase == p) for p in APPROACH_ORDER]
            vec += [min(self._green_elapsed / 45.0, 1.0), float(self._detect_emergency() is not None)]
            vec += [min(self._red_age[p] / 180.0, 1.0) for p in APPROACH_ORDER]
        elif self.augmented_state:
            vec += [float(self._last_phase == "NS"), float(self._last_phase == "EW"),
                    min(self._green_elapsed / 90.0, 1.0),
                    float(self._detect_emergency() is not None)]
        return np.array(vec, dtype=np.float32)

    def _pressure_reward(self):
        """Reward = negative total queue (halting vehicle count) across all
        incoming lanes.

        The doc specifies a PressLight-style reward (queue differential
        between incoming and outgoing lanes). During development that exact
        formulation was tried first and found to give the agent almost no
        actionable signal here: summed globally across all 8 approaches, the
        pressure metric barely changes based on which single phase is
        currently green, so with a short (~10k-step) training budget the
        DQN consistently collapsed onto a single action rather than learning
        to serve whichever approach is congested. This simpler, direct
        "minimize total queue" reward gives immediate, phase-specific
        feedback (serving a congested approach visibly drops this value the
        very next step) and is what Genders & Razavi's original DQN signal
        controller work used — it converges far faster on a small compute
        budget. Swap back to a true per-movement PressLight formulation
        (documented in Zheng et al.) once you're doing the doc's full
        500k-step training run, where its better asymptotic behavior can
        actually be realized."""
        in_q = sum(traci.lane.getLastStepHaltingNumber(l) for l in INCOMING_LANES)
        # scaled down: with gamma close to 1 and long macro-steps (15-90s), the
        # discounted-return magnitude was dwarfing the actual advantage between
        # actions (confirmed by inspecting Q(s,a): differences between the 8
        # actions were ~1-2 against a baseline of 40-150), so the network was
        # effectively only learning V(s), not which action to prefer. Scaling
        # keeps relative ordering identical but gives the action-relevant
        # signal a fighting chance against a lower discount factor (see gamma
        # in train.py).
        return -float(in_q) / 10.0

    def _detect_emergency(self):
        """Returns the approach ('N'/'S'/'E'/'W') of the nearest emergency
        vehicle within EMERGENCY_PROXIMITY_M, or None."""
        if not self.emergency_enabled:
            return None
        try:
            veh_ids = tuple(self._emergency_ids)
        except traci.TraCIException:
            return None
        nearest = (float("inf"), None)
        for vid in veh_ids:
            try:
                if traci.vehicle.getVehicleClass(vid) != "emergency":
                    continue
                lane = traci.vehicle.getLaneID(vid)
                dist_to_junction = traci.vehicle.getLanePosition(vid)
                lane_len = traci.lane.getLength(lane)
                remaining = lane_len - dist_to_junction
                if remaining > EMERGENCY_PROXIMITY_M:
                    continue
                for approach, lanes in APPROACH_LANES.items():
                    if lane in lanes:
                        if remaining < nearest[0]:
                            nearest = (remaining, approach)
            except traci.TraCIException:
                continue
        return nearest[1]

    def _set_phase(self, phase_name):
        state = APPROACH_SIGNALS[phase_name] if self.single_approach else NS_GREEN if phase_name == "NS" else EW_GREEN
        traci.trafficlight.setRedYellowGreenState("center", state)

    def _emergency_phase(self, approach):
        return approach if self.single_approach else "NS" if approach in ("N", "S") else "EW"

    def _other_demand(self, phase):
        if self.single_approach:
            return [p for p in APPROACH_ORDER if p != phase and
                    any(traci.lane.getLastStepVehicleNumber(l) for l in APPROACH_LANES[p])]
        opposite = INCOMING_LANES[4:] if phase == "NS" else INCOMING_LANES[:4]
        return ["EW" if phase == "NS" else "NS"] if any(traci.lane.getLastStepVehicleNumber(l) for l in opposite) else []

    def _record_metrics_tick(self):
        """Called once per simulated second; accumulates the stats used for
        evaluation (avg queue, avg wait, throughput). Throughput is tallied
        every tick (cheap, one TraCI call), but the more expensive per-lane
        queue sample and per-vehicle waiting-time poll are subsampled to
        every `metrics_sample_every` seconds to keep this affordable."""
        if not self.collect_metrics:
            # still track throughput cheaply even when full metrics are off
            self._metrics["throughput"] += traci.simulation.getArrivedNumber()
            return

        arrived = traci.simulation.getArrivedNumber()
        self._metrics["throughput"] += arrived
        for vid in traci.simulation.getArrivedIDList():
            wt = self._metrics["_last_wait"].pop(vid, 0.0)
            self._metrics["completed_wait_times"].append(wt)

        if self._sim_time % self.metrics_sample_every != 0:
            return
        halting = sum(traci.lane.getLastStepHaltingNumber(l) for l in INCOMING_LANES)
        self._metrics["queue_samples"].append(halting)
        for vid in traci.vehicle.getIDList():
            try:
                self._metrics["_last_wait"][vid] = traci.vehicle.getAccumulatedWaitingTime(vid)
            except traci.TraCIException:
                pass

    def _tick(self):
        """Advances the sim by one second and runs all per-second hooks:
        metrics collection, draining pending dashboard spawn requests, and
        (if attached) streaming a vehicle snapshot for live animation."""
        if self._sim_time >= self.max_steps or self.stop_requested():
            return False
        self._drain_spawns()
        traci.simulationStep()
        self._sim_time += 1
        for p in APPROACH_ORDER:
            self._red_age[p] = 0 if self._signal_stage == "green" and self._last_phase == p else self._red_age[p] + 1
        self._queue_area += sum(traci.lane.getLastStepHaltingNumber(l) for l in INCOMING_LANES)
        self._collisions += traci.simulation.getCollidingVehiclesNumber()
        self._teleports += traci.simulation.getStartingTeleportNumber()
        self._departed += traci.simulation.getDepartedNumber()
        for vid in traci.simulation.getDepartedIDList():
            if traci.vehicle.getVehicleClass(vid) == "emergency":
                self._emergency_ids.add(vid)
        self._emergency_ids.difference_update(traci.simulation.getArrivedIDList())
        self._record_metrics_tick()
        if self._tick_callback:
            self._tick_callback(self._sim_time)
            time.sleep(self.playback_delay)
        return True

    def _transition(self, target_phase, green_duration):
        """Runs yellow + all-red intergreen if switching phase, then holds
        the target green for green_duration seconds (stepping the sim)."""
        if target_phase != self._last_phase:
            self._next_phase = target_phase
            yellow = (APPROACH_SIGNALS[self._last_phase].replace("G", "y") if self.single_approach
                      else NS_YELLOW if self._last_phase == "NS" else EW_YELLOW)
            traci.trafficlight.setRedYellowGreenState("center", yellow)
            self._signal_stage = "yellow"
            for _ in range(YELLOW_TIME):
                if not self._tick():
                    return
            traci.trafficlight.setRedYellowGreenState("center", ALL_RED)
            self._signal_stage = "all-red"
            for _ in range(ALL_RED_TIME):
                if not self._tick():
                    return
            self._green_elapsed = 0

        self._set_phase(target_phase)
        self._last_phase = target_phase
        self._signal_stage = "green"
        self._next_phase = None
        for remaining in range(green_duration, 0, -1):
            self._remaining = remaining
            if not self._tick():
                break
            self._green_elapsed += 1
            emergency = self._detect_emergency()
            if emergency:
                forced = self._emergency_phase(emergency)
                self._preempted = True
                if forced != target_phase:
                    # Return to the decision loop immediately; the next decision
                    # applies the full yellow/all-red clearance before preemption.
                    break
            if self._green_elapsed >= (45 if self.single_approach else 90) and self._other_demand(target_phase):
                break
        self._remaining = 0

    def get_episode_metrics(self):
        """Returns aggregate metrics for the episode so far: avg queue length
        (vehicles), avg wait time (s) for vehicles that completed their trip,
        and throughput (vehicles that reached their destination)."""
        q = self._metrics["queue_samples"]
        w = self._metrics["completed_wait_times"]
        return {
            "avg_queue_length": self._queue_area / max(1, self._sim_time),
            "avg_wait_time_s": (sum(w) / len(w)) if w else 0.0,
            "throughput_vehicles": self._metrics["throughput"],
            "sim_time_s": self._sim_time,
            "departed_vehicles": self._departed,
            "active_vehicles": traci.vehicle.getIDCount(),
            "pending_vehicles": len(traci.simulation.getPendingVehicles()),
            "teleported_vehicles": self._teleports,
            "collision_vehicle_events": self._collisions,
            "total_queue_vehicle_seconds": self._queue_area,
        }

    # ------------------------------------------------------------------ #
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._close_sumo()
        if seed is not None:
            self._sumo_seed = seed
        else:
            self._sumo_seed = int(getattr(self.np_random, 'integers', getattr(self.np_random, 'randint'))(0, 2**30))
        self._start_sumo()
        self._sim_time = 0
        self._episode_step = 0
        self._last_phase = "N" if self.single_approach else "NS"
        self._red_age = {p: 0 for p in APPROACH_ORDER}
        self._next_phase = None
        self._green_elapsed = 0
        self._signal_stage = "green"
        self._remaining = 0
        self._preempted = False
        self._queue_area = 0.0
        self._collisions = self._teleports = self._departed = 0
        self._emergency_ids.clear()
        self._known_routes.clear()
        self._metrics = {
            "queue_samples": [],
            "throughput": 0,
            "completed_wait_times": [],
            "_last_wait": {},
        }
        self._set_phase(self._last_phase)
        self._tick()
        obs = self._get_state()
        return obs, {}

    def step(self, action):
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid signal action: {action}")
        phase, duration = self.actions[int(action)]

        emergency_approach = self._detect_emergency()
        self._preempted = emergency_approach is not None
        if emergency_approach is not None:
            phase, duration = self._emergency_phase(emergency_approach), 10 if self.single_approach else DURATION_BUCKETS[0]
        else:
            waiting = self._other_demand(self._last_phase)
            if self.single_approach:
                oldest = max(waiting, key=lambda p: self._red_age[p]) if waiting else None
                if oldest and (self._red_age[oldest] >= 90 or self._green_elapsed >= 45):
                    phase, duration = oldest, 10
            elif self._green_elapsed >= 90 and waiting:
                phase, duration = waiting[0], DURATION_BUCKETS[0]

        before_time, before_queue = self._sim_time, self._queue_area
        self._transition(phase, duration)

        obs = self._get_state()
        reward = -(self._queue_area - before_queue) / max(1, self._sim_time - before_time) / 10.0

        self._episode_step += 1
        terminated = False
        truncated = self._sim_time >= self.max_steps or self.stop_requested()
        try:
            if traci.simulation.getMinExpectedNumber() <= 0:
                terminated = True
        except traci.TraCIException:
            terminated = True

        info = {
            "sim_time": self._sim_time,
            "phase": self._last_phase,
            "duration": self._sim_time - before_time,
            "emergency_preemption": self._preempted,
        }
        return obs, reward, terminated, truncated, info

    def close(self):
        self._close_sumo()
        if self._route_workspace:
            self._route_workspace.cleanup()
            self._route_workspace = None

    def render(self):
        pass
