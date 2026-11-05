"""Vision-Actuated Hierarchical Priority Traffic Controller.

Implements the 3-Tier Intelligent Priority Control Hierarchy:
  - Rule 1: Emergency Vehicle Preemption (Highest Priority / Safety Critical)
  - Rule 2: Density-Based Dynamic Extension with South Line Prioritization
  - Rule 3: Traditional Fallback Cycle (60s Predictable Rotation on Low Traffic)
"""
import os
import sys
from typing import Dict, Any, Tuple

APPROACH_ORDER = ["N", "E", "S", "W"]
APPROACH_DURATIONS = [10, 20, 30, 45]
APPROACH_ACTIONS = [(p, d) for p in APPROACH_ORDER for d in APPROACH_DURATIONS]


class VisionActuatedPriorityPolicy:
    """3-Tier Intelligent Signal Controller actuated by computer vision and queue sensing."""

    name = "vision_actuated"

    def __init__(self, south_priority_multiplier: float = 1.6, low_traffic_threshold: float = 1.0):
        self.south_priority_multiplier = south_priority_multiplier
        self.low_traffic_threshold = low_traffic_threshold
        self.reset()

    def reset(self):
        self.last_phase = "N"
        self.active_rule = "TRADITIONAL_FALLBACK_60S"
        self.fallback_approach_idx = 0
        self.fallback_half_step = 0  # 0 or 1 (each 30s to total 60s per approach)
        self.south_consecutive_extensions = 0
        self.max_south_extensions = 3  # Safeguard cap to prevent starvation of other lanes

    def act(self, obs, camera_data: Dict[str, Any] = None) -> int:
        """Evaluates traffic state and returns discrete action index (0-15).

        Observation layout (18 dimensions when single_approach=True):
          - obs[0:8]: Incoming lane densities (2 lanes per approach: N, S, E, W)
          - obs[8:12]: One-hot active phase [N, E, S, W]
          - obs[12]: Elapsed green fraction
          - obs[13]: Emergency presence flag in simulation (1.0 if emergency < 200m)
          - obs[14:18]: Red-light waiting age for [N, E, S, W]
        """
        import numpy as np

        # 1. Parse queue counts per approach (scale normalized [0, 1] by 60)
        # obs order: N: [0,1], S: [2,3], E: [4,5], W: [6,7]
        n_count = float(sum(obs[0:2])) * 60.0
        s_count = float(sum(obs[2:4])) * 60.0
        e_count = float(sum(obs[4:6])) * 60.0
        w_count = float(sum(obs[6:8])) * 60.0
        counts = {"N": n_count, "S": s_count, "E": e_count, "W": w_count}

        # Check vision telemetry if camera_data provided
        vision_emergency = None
        if camera_data:
            c_counts = camera_data.get("counts", {})
            if c_counts:
                # Merge vision counts if available
                counts["N"] = max(counts["N"], float(c_counts.get("N", 0)))
                counts["S"] = max(counts["S"], float(c_counts.get("S", 0)))
                counts["E"] = max(counts["E"], float(c_counts.get("E", 0)))
                counts["W"] = max(counts["W"], float(c_counts.get("W", 0)))
            emg = camera_data.get("emergency", {})
            if emg and emg.get("detected"):
                vision_emergency = emg.get("approach")

        sim_emergency_flag = (len(obs) > 13 and obs[13] > 0.5)
        total_traffic = sum(counts.values())

        # Determine current active approach from one-hot or default
        current_phase = self.last_phase
        if len(obs) >= 12:
            one_hot = list(obs[8:12])
            if any(v > 0.5 for v in one_hot):
                current_phase = APPROACH_ORDER[int(one_hot.index(max(one_hot)))]

        # =====================================================================
        # RULE 1: EMERGENCY VEHICLE PREEMPTION (Highest Priority / Safety Critical)
        # =====================================================================
        # If an emergency vehicle (ambulance) is detected on any approach
        if sim_emergency_flag or vision_emergency:
            target_approach = vision_emergency or current_phase
            # In simulation, determine which approach has emergency
            if not vision_emergency and len(obs) >= 18:
                # If emergency flag is set, pick approach with highest emergency probability
                target_approach = current_phase

            self.active_rule = f"RULE_1_EMERGENCY_PREEMPTION ({target_approach})"
            self.last_phase = target_approach
            # Grant immediate green: pick 20s or 30s bucket to swiftly clear corridor
            approach_idx = APPROACH_ORDER.index(target_approach)
            duration_bucket = 1  # 20s
            return approach_idx * 4 + duration_bucket

        # =====================================================================
        # RULE 3: TRADITIONAL FALLBACK CYCLE (Low Traffic / Night Mode / Empty Roads)
        # =====================================================================
        # If no vehicles or low traffic detected (<= low_traffic_threshold)
        if total_traffic <= self.low_traffic_threshold:
            self.active_rule = "RULE_3_TRADITIONAL_FALLBACK_60S"
            # Cycle through N -> E -> S -> W, granting 60 seconds (two 30s blocks)
            target_approach = APPROACH_ORDER[self.fallback_approach_idx]
            self.last_phase = target_approach

            # Duration index 2 corresponds to 30 seconds (30s + 30s = 60s total)
            duration_bucket = 2  # 30s

            if self.fallback_half_step == 0:
                # First 30s half of the 60s cycle
                self.fallback_half_step = 1
            else:
                # Second 30s half completed; advance to next approach for the next 60s
                self.fallback_half_step = 0
                self.fallback_approach_idx = (self.fallback_approach_idx + 1) % 4

            approach_idx = APPROACH_ORDER.index(target_approach)
            return approach_idx * 4 + duration_bucket

        # Reset fallback half-step when traffic emerges
        self.fallback_half_step = 0

        # =====================================================================
        # RULE 2: DENSITY-BASED DYNAMIC EXTENSION (Peak Hour & South Line Priority)
        # =====================================================================
        # Continuously monitor vehicle queues. If South line accumulates high
        # density, bypass standard timers to dynamically extend green.
        self.active_rule = "RULE_2_DENSITY_DYNAMIC_EXTENSION"

        # Apply South Line Congestion Priority Multiplier
        effective_scores = {
            "N": counts["N"],
            "E": counts["E"],
            "S": counts["S"] * self.south_priority_multiplier,  # South Line Priority
            "W": counts["W"],
        }

        # Incorporate red waiting age to prevent extreme starvation
        ages = [float(x) * 180.0 for x in obs[14:18]] if len(obs) >= 18 else [0.0] * 4
        for i, appr in enumerate(APPROACH_ORDER):
            if effective_scores[appr] > 0:
                effective_scores[appr] += float(ages[i]) * 0.15

        # Check if South line is heavily congested and currently green
        is_south_congested = counts["S"] >= 4.0
        if current_phase == "S" and is_south_congested and self.south_consecutive_extensions < self.max_south_extensions:
            # DYNAMIC EXTENSION FOR SOUTH LINE
            self.south_consecutive_extensions += 1
            self.active_rule = f"RULE_2_SOUTH_DYNAMIC_EXTENSION (Step {self.south_consecutive_extensions}, {counts['S']:.0f} veh)"
            self.last_phase = "S"
            approach_idx = APPROACH_ORDER.index("S")
            # Allocate 30s or 45s extension depending on queue size
            duration_bucket = 3 if counts["S"] >= 10 else 2
            return approach_idx * 4 + duration_bucket

        # Otherwise pick the approach with the highest effective score
        selected_approach = max(APPROACH_ORDER, key=lambda p: effective_scores[p])
        if selected_approach == "S":
            self.south_consecutive_extensions += 1
            if is_south_congested:
                self.active_rule = f"RULE_2_SOUTH_PRIORITY_ACTUATED ({counts['S']:.0f} veh)"
        else:
            self.south_consecutive_extensions = 0
            self.active_rule = f"RULE_2_DENSITY_ACTUATED ({selected_approach})"

        self.last_phase = selected_approach
        n_selected = counts[selected_approach]

        # Allocate dynamic duration based on congestion level
        if n_selected < 4:
            duration_bucket = 0  # 10s
        elif n_selected < 10:
            duration_bucket = 1  # 20s
        elif n_selected < 18:
            duration_bucket = 2  # 30s
        else:
            duration_bucket = 3  # 45s (max green extension)

        approach_idx = APPROACH_ORDER.index(selected_approach)
        return approach_idx * 4 + duration_bucket
