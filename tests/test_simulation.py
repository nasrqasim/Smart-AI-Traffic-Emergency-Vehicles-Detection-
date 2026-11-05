"""Integration checks using real SUMO and rule-based vision policy validation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl_env.traffic_env import TrafficSignalEnv, ALL_RED, NS_GREEN, EW_GREEN
from rl_env.traffic_env import APPROACH_ORDER, APPROACH_SIGNALS
from rl_env.traffic_env import traci
from eval.vision_actuated_policy import VisionActuatedPriorityPolicy


class SimulationChecks(unittest.TestCase):
    def setUp(self):
        self.env = TrafficSignalEnv(max_steps=240, collect_metrics=True, augmented_state=True)
        self.env.reset(seed=812)

    def tearDown(self):
        self.env.close()

    def test_clearance_and_episode_boundary(self):
        signals = []
        self.env.playback_delay = 0
        self.env.set_tick_callback(lambda _: signals.append(traci.trafficlight.getRedYellowGreenState("center")))
        obs, _, _, _, _ = self.env.step(4)
        self.assertEqual(signals[:3], ["yyyyrrrryyyyrrrr"] * 3)
        self.assertEqual(signals[3:5], [ALL_RED] * 2)
        self.assertEqual(signals[5:], [EW_GREEN] * 15)
        self.assertEqual(obs.shape, (12,))
        self.assertTrue(self.env.observation_space.contains(obs))
        while self.env._sim_time < 240:
            _, _, _, truncated, _ = self.env.step(3)
        self.assertTrue(truncated)
        self.assertEqual(self.env._sim_time, 240)

    def test_emergency_overrides_with_clearance(self):
        traci.route.add("test_emergency_route", ["E2C", "C2W"])
        traci.vehicle.add("test_emergency", "test_emergency_route", typeID="emergency", departPos="100")
        self.env._tick()
        self.assertEqual(self.env._detect_emergency(), "E")
        _, _, _, _, info = self.env.step(0)
        self.assertTrue(info["emergency_preemption"])
        self.assertEqual(info["phase"], "EW")
        self.assertEqual(traci.trafficlight.getRedYellowGreenState("center"), EW_GREEN)

    def test_max_green_serves_opposing_demand(self):
        traci.route.add("test_opposition", ["E2C", "C2W"])
        traci.vehicle.add("test_car", "test_opposition", typeID="car", departPos="100")
        self.env._tick()
        self.env._green_elapsed = 90
        _, _, _, _, info = self.env.step(0)
        self.assertEqual(info["phase"], "EW")

    def test_reset_allows_repeat_spawn_routes(self):
        self.env._spawn_one({"road": "N", "vehicle_type": "car"})
        self.env.reset(seed=813)
        self.env._spawn_one({"road": "N", "vehicle_type": "ambulance"})
        self.env._tick()
        self.assertIn("spawn_N2C", traci.route.getIDList())
        snapshot = self.env.get_vehicle_snapshot()
        self.assertTrue(snapshot)
        self.assertTrue(all(k in snapshot[0] for k in ("x", "y", "angle", "length", "width")))

    def test_invalid_actions(self):
        with self.assertRaises(ValueError):
            self.env.step(8)


class ExclusiveApproachChecks(unittest.TestCase):
    def setUp(self):
        self.env = TrafficSignalEnv(max_steps=600, single_approach=True, collect_metrics=True)
        self.env.reset(seed=32)
        self.env.playback_delay = 0

    def tearDown(self):
        self.env.close()

    def test_signal_groups_match_actual_network_approaches(self):
        links = traci.trafficlight.getControlledLinks("center")
        for index, road in enumerate(APPROACH_ORDER):
            for connections in links[index*4:index*4+4]:
                self.assertTrue(connections)
                self.assertTrue(all(link[0].startswith(road + "2C_") for link in connections))

    def test_exactly_one_road_green_at_every_tick(self):
        signals = []
        self.env.set_tick_callback(lambda _: signals.append(traci.trafficlight.getRedYellowGreenState("center")))
        for phase in range(4):
            obs, _, _, _, _ = self.env.step(phase * 4)
            self.assertEqual(obs.shape, (18,))
        for signal in signals:
            green_roads = [p for i, p in enumerate(APPROACH_ORDER) if "G" in signal[i*4:i*4+4]]
            self.assertLessEqual(len(green_roads), 1, signal)
        self.assertEqual(self.env.get_episode_metrics()["collision_vehicle_events"], 0)

    def test_clearance_between_individual_roads(self):
        signals = []
        self.env.set_tick_callback(lambda _: signals.append(traci.trafficlight.getRedYellowGreenState("center")))
        self.env.step(4)  # North -> East
        self.assertEqual(signals[:3], ["yyyyrrrrrrrrrrrr"] * 3)
        self.assertEqual(signals[3:5], [ALL_RED] * 2)
        self.assertTrue(all(s == APPROACH_SIGNALS["E"] for s in signals[5:]))

    def test_exclusive_emergency_priority(self):
        traci.route.add("priority_west", ["W2C", "C2E"])
        traci.vehicle.add("priority_west_1", "priority_west", typeID="emergency", departPos="100")
        self.env._tick()
        _, _, _, _, info = self.env.step(0)
        self.assertEqual(info["phase"], "W")
        self.assertTrue(info["emergency_preemption"])
        self.assertEqual(traci.trafficlight.getRedYellowGreenState("center"), APPROACH_SIGNALS["W"])

    def test_red_age_prevents_starvation(self):
        traci.route.add("waiting_south", ["S2C", "C2N"])
        traci.vehicle.add("waiting_south_1", "waiting_south", typeID="car", departPos="100")
        self.env._tick()
        self.env._red_age["S"] = 120
        _, _, _, _, info = self.env.step(0)
        self.assertEqual(info["phase"], "S")


class VisionActuatedPolicyChecks(unittest.TestCase):
    def setUp(self):
        self.policy = VisionActuatedPriorityPolicy()

    def test_rule_1_emergency_preemption(self):
        camera_data = {"emergency": {"detected": True, "approach": "S", "type": "ambulance"}}
        obs = [0.0] * 18
        action = self.policy.act(obs, camera_data=camera_data)
        # S approach index is 2 in [N, E, S, W] -> actions 8..11
        self.assertTrue(8 <= action <= 11)
        self.assertIn("EMERGENCY", self.policy.active_rule)

    def test_rule_2_south_line_priority_dynamic_extension(self):
        obs = [0.0] * 18
        obs[2] = 0.2  # 12 vehicles on S
        obs[3] = 0.1  # 6 vehicles on S -> total 18 vehicles
        obs[0] = 0.05  # 3 vehicles on N
        action = self.policy.act(obs)
        # S approach index is 2 -> actions 8..11
        self.assertTrue(8 <= action <= 11)
        self.assertIn("SOUTH", self.policy.active_rule)

    def test_rule_3_traditional_fallback_cycle_60s(self):
        obs = [0.0] * 18
        # Step 1: N first 30s
        act1 = self.policy.act(obs)
        self.assertEqual(act1, 0 * 4 + 2)
        self.assertIn("FALLBACK", self.policy.active_rule)
        # Step 2: N second 30s (completing 60s total)
        act2 = self.policy.act(obs)
        self.assertEqual(act2, 0 * 4 + 2)
        # Step 3: Rotates to E (first 30s)
        act3 = self.policy.act(obs)
        self.assertEqual(act3, 1 * 4 + 2)


if __name__ == "__main__":
    unittest.main()
