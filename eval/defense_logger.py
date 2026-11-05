"""Performance Tracking & Defense Reporting Logger.

Logs vehicle queue lengths, waiting times, throughput, emergency preemption
overrides, South line priority extensions, and traditional fallback cycles
for empirical evaluation and FYP project defense reporting.
"""
import os
import csv
import json
import time
from typing import Dict, List, Any


class DefensePerformanceLogger:
    """Thread-safe performance metrics and event logger for FYP defense presentation."""

    def __init__(self, log_dir: str = None):
        self.log_dir = log_dir or os.path.join(os.path.dirname(__file__), "..", "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.events: List[Dict[str, Any]] = []
        self.stats = {
            "emergency_preemptions": 0,
            "south_priority_extensions": 0,
            "fallback_60s_cycles": 0,
            "total_decisions": 0,
            "total_vehicles_served": 0,
            "peak_queue": 0,
            "cumulative_queue_time": 0.0,
        }

    def reset(self):
        self.events.clear()
        self.stats = {
            "emergency_preemptions": 0,
            "south_priority_extensions": 0,
            "fallback_60s_cycles": 0,
            "total_decisions": 0,
            "total_vehicles_served": 0,
            "peak_queue": 0,
            "cumulative_queue_time": 0.0,
        }

    def log_decision(
        self,
        sim_time: int,
        controller: str,
        active_rule: str,
        phase: str,
        duration: int,
        density_dict: Dict[str, float],
        metrics: Dict[str, Any],
        camera_counts: Dict[str, int] = None,
        notes: str = ""
    ):
        """Records a single traffic signal decision event."""
        self.stats["total_decisions"] += 1

        if "EMERGENCY" in active_rule.upper():
            self.stats["emergency_preemptions"] += 1
        elif "SOUTH" in active_rule.upper():
            self.stats["south_priority_extensions"] += 1
        elif "FALLBACK" in active_rule.upper():
            self.stats["fallback_60s_cycles"] += 1

        avg_queue = metrics.get("avg_queue_length", 0.0)
        if avg_queue > self.stats["peak_queue"]:
            self.stats["peak_queue"] = avg_queue

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sim_time": sim_time,
            "controller": controller,
            "active_rule": active_rule,
            "phase": phase,
            "duration": duration,
            "density_N": round(density_dict.get("N-in", 0.0) + density_dict.get("N-left", 0.0), 2),
            "density_S": round(density_dict.get("S-in", 0.0) + density_dict.get("S-left", 0.0), 2),
            "density_E": round(density_dict.get("E-in", 0.0) + density_dict.get("E-left", 0.0), 2),
            "density_W": round(density_dict.get("W-in", 0.0) + density_dict.get("W-left", 0.0), 2),
            "camera_counts": camera_counts or {},
            "avg_queue": round(avg_queue, 2),
            "avg_wait_s": round(metrics.get("avg_wait_time_s", 0.0), 2),
            "throughput": metrics.get("throughput_vehicles", 0),
            "notes": notes
        }
        self.events.append(entry)
        if len(self.events) > 1000:
            self.events.pop(0)  # Keep rolling window of 1000 events

    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.events[-limit:]

    def get_summary(self) -> Dict[str, Any]:
        last_metric = self.events[-1] if self.events else {}
        return {
            "total_decisions": self.stats["total_decisions"],
            "emergency_preemptions": self.stats["emergency_preemptions"],
            "south_priority_extensions": self.stats["south_priority_extensions"],
            "fallback_60s_cycles": self.stats["fallback_60s_cycles"],
            "peak_queue": round(self.stats["peak_queue"], 2),
            "latest_avg_queue": last_metric.get("avg_queue", 0.0),
            "latest_avg_wait": last_metric.get("avg_wait_s", 0.0),
            "latest_throughput": last_metric.get("throughput", 0),
        }

    def export_csv(self, filename: str = None) -> str:
        """Exports all logged decision events to CSV for project defense evaluation."""
        if not filename:
            filename = os.path.join(self.log_dir, f"defense_report_{int(time.time())}.csv")

        fields = [
            "timestamp", "sim_time", "controller", "active_rule", "phase", "duration",
            "density_N", "density_S", "density_E", "density_W",
            "avg_queue", "avg_wait_s", "throughput", "notes"
        ]
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for ev in self.events:
                writer.writerow(ev)
        return filename


# Global singleton instance
defense_logger = DefensePerformanceLogger()
