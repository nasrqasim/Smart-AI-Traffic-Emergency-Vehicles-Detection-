"""
Rule-based baseline controllers, expressed as functions obs -> action_index
so they can be dropped into the same TrafficSignalEnv/ACTIONS space as the
DQN agent for an apples-to-apples comparison.

- FixedTimePolicy: Webster-style fixed cycle, alternates NS/EW with a
  constant duration regardless of measured density (matches "(a) Webster's
  fixed-time optimum" baseline in the doc).
- ActuatedPolicy: gap-out / density-extension logic, switches to whichever
  approach has the larger queue and scales green duration with density
  (matches "(b) actuated control" baseline).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rl_env"))
from traffic_env import ACTIONS, DURATION_BUCKETS  # noqa: E402
from traffic_env import APPROACH_ACTIONS, APPROACH_ORDER
from vision_actuated_policy import VisionActuatedPriorityPolicy  # noqa: E402


class ApproachFixedPolicy:
    name = "fixed_time"

    def reset(self):
        self.index = 0

    def __init__(self):
        self.reset()

    def act(self, obs):
        action = self.index * 4 + 1
        self.index = (self.index + 1) % 4
        return action


class ApproachAdaptivePolicy:
    """Queue demand plus red age; each selected road receives an exclusive green."""
    name = "actuated"

    def reset(self):
        self.last = None

    def __init__(self):
        self.reset()

    def act(self, obs):
        import numpy as np
        # Incoming state order N,S,E,W; action order N,E,S,W.
        counts = [float(sum(obs[i:i+2])) * 60 for i in (0, 4, 2, 6)]
        ages = obs[14:18] * 180 if len(obs) >= 18 else np.zeros(4)
        scores = [n + float(age) * .2 if n > 0 else 0 for n, age in zip(counts, ages)]
        index = max(range(4), key=lambda i: (scores[i], i != self.last))
        self.last = index
        n = counts[index]
        bucket = 0 if n < 5 else 1 if n < 12 else 2 if n < 22 else 3
        return index * 4 + bucket

# index lookup: ACTIONS = [("NS",15),("NS",35),("NS",60),("NS",90),
#                            ("EW",15),("EW",35),("EW",60),("EW",90)]
NS_INDEX = {d: i for i, (p, d) in enumerate(ACTIONS) if p == "NS"}
EW_INDEX = {d: i for i, (p, d) in enumerate(ACTIONS) if p == "EW"}


class FixedTimePolicy:
    """Ignores the observation entirely; alternates a constant-duration
    NS/EW cycle. This is the classic Webster fixed-time baseline."""

    name = "fixed_time"

    def __init__(self, duration=35):
        self.duration = duration
        self._next = "NS"

    def reset(self):
        self._next = "NS"

    def act(self, obs):
        phase = self._next
        self._next = "EW" if self._next == "NS" else "NS"
        idx = NS_INDEX[self.duration] if phase == "NS" else EW_INDEX[self.duration]
        return idx


class ActuatedPolicy:
    """Density-aware gap-out logic: switches to the approach with the
    larger measured queue, and scales the green duration with how
    congested that approach is (longer green for heavier density).

    Ties (including both approaches sitting at the sensor's saturation
    ceiling, where the raw density signal alone can no longer tell them
    apart) are broken by alternating rather than defaulting to one side —
    otherwise a saturated intersection would starve one approach forever,
    which is a textbook failure mode of naive actuated control this
    baseline is meant to represent realistically, not accidentally trigger
    via a coin-flip default."""

    name = "actuated"

    def __init__(self, max_consecutive_same_phase=3):
        self.max_consecutive_same_phase = max_consecutive_same_phase
        self._last_phase = None
        self._consecutive = 0

    def reset(self):
        self._last_phase = None
        self._consecutive = 0

    def act(self, obs):
        # obs layout: [N0,N1, S0,S1, E0,E1, W0,W1] (see traffic_env.INCOMING_LANES)
        ns_density = obs[0] + obs[1] + obs[2] + obs[3]
        ew_density = obs[4] + obs[5] + obs[6] + obs[7]

        tied = abs(ns_density - ew_density) < 1e-6
        forced_switch = (self._last_phase is not None and
                          self._consecutive >= self.max_consecutive_same_phase)
        if forced_switch:
            phase = "EW" if self._last_phase == "NS" else "NS"
        elif tied and self._last_phase is not None:
            phase = "EW" if self._last_phase == "NS" else "NS"  # alternate on ties
        else:
            phase = "NS" if ns_density >= ew_density else "EW"

        if phase == self._last_phase:
            self._consecutive += 1
        else:
            self._consecutive = 1
        self._last_phase = phase

        density = max(ns_density, ew_density) / 4.0  # normalize back to [0,1]

        # pick duration bucket proportional to density
        if density < 0.25:
            duration = DURATION_BUCKETS[0]
        elif density < 0.5:
            duration = DURATION_BUCKETS[1]
        elif density < 0.75:
            duration = DURATION_BUCKETS[2]
        else:
            duration = DURATION_BUCKETS[3]

        idx = NS_INDEX[duration] if phase == "NS" else EW_INDEX[duration]
        return idx


class DQNPolicy:
    """Wraps a trained Stable-Baselines3 DQN model to the same act(obs) interface."""

    name = "dqn"

    def __init__(self, model_path):
        from stable_baselines3 import DQN
        self.model = DQN.load(model_path)

    def reset(self):
        pass

    def act(self, obs):
        action, _ = self.model.predict(obs[:self.model.observation_space.shape[0]], deterministic=True)
        return int(action)
