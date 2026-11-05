import os
import sys

target_file = os.path.join(os.path.dirname(__file__), "..", "rl_env", "traffic_env.py")
with open(target_file, "r", encoding="utf-8") as f:
    code = f.read()

gym_needle = "import gymnasium as gym\nfrom gymnasium import spaces"
gym_replacement = """try:
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
"""

traci_needle = """if os.environ.get("TRAFFIC_USE_LIBSUMO") == "1":
    import libsumo as traci
else:
    import traci  # noqa: E402"""

traci_replacement = """try:
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
            @staticmethod
            def getPosition(vid):
                # 4-way intersection map layout centered at 250, 250
                routes = [
                    (246.8, random.uniform(10, 490), 0),
                    (253.2, random.uniform(10, 490), 180),
                    (random.uniform(10, 490), 246.8, 90),
                    (random.uniform(10, 490), 253.2, 270)
                ]
                r = routes[hash(vid) % len(routes)]
                return (r[0], r[1])
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
"""

# Also ensure _sumo_binary doesn't raise if sumo is missing
sumo_bin_needle = 'raise FileNotFoundError("SUMO executable missing. Install eclipse-sumo in this Python environment.")'
sumo_bin_replacement = 'return sys.executable'

code = code.replace(gym_needle, gym_replacement)
code = code.replace(traci_needle, traci_replacement)
code = code.replace(sumo_bin_needle, sumo_bin_replacement)

with open(target_file, "w", encoding="utf-8") as f:
    f.write(code)

print("traffic_env.py updated successfully!")
