"""
Runs fixed-time, actuated, and DQN controllers on the same SUMO scenario(s)
and compares average wait time, average queue length, and throughput —
matching the doc's Section 3.5 "Agent performance in simulation" evaluation
plan.

Usage:
    python eval/evaluate.py --model models/dqn_traffic.zip --episodes 3 --episode-seconds 1800
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rl_env"))
from traffic_env import TrafficSignalEnv  # noqa: E402
from baselines import ApproachFixedPolicy, ApproachAdaptivePolicy, DQNPolicy  # noqa: E402


def run_policy(policy, episode_seconds, episodes, base_seed, randomize_routes=False):
    results = []
    for ep in range(episodes):
        env = TrafficSignalEnv(max_steps=episode_seconds, seed=base_seed + ep, collect_metrics=True,
                               augmented_state=True, randomize_routes=randomize_routes, single_approach=True)
        obs, _ = env.reset(seed=base_seed + ep)
        policy.reset()
        terminated = truncated = False
        emergency_events = 0
        while not (terminated or truncated):
            action = policy.act(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            if info.get("emergency_preemption"):
                emergency_events += 1
        m = env.get_episode_metrics()
        m["emergency_preemptions"] = emergency_events
        results.append(m)
        env.close()
    return results


def summarize(name, results):
    n = len(results)
    avg_wait = sum(r["avg_wait_time_s"] for r in results) / n
    avg_queue = sum(r["avg_queue_length"] for r in results) / n
    avg_throughput = sum(r["throughput_vehicles"] for r in results) / n
    return {
        "controller": name,
        "avg_wait_time_s": round(avg_wait, 2),
        "avg_queue_length_vehicles": round(avg_queue, 2),
        "avg_throughput_vehicles": round(avg_throughput, 1),
        "episodes": n,
        "avg_active_at_end": round(sum(r["active_vehicles"] for r in results) / n, 1),
        "avg_pending_at_end": round(sum(r["pending_vehicles"] for r in results) / n, 1),
        "total_collision_vehicle_events": sum(r["collision_vehicle_events"] for r in results),
        "total_teleported_vehicles": sum(r["teleported_vehicles"] for r in results),
        "episode_results": results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/dqn_approach_v3.zip")
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--episode-seconds", type=int, default=1800)
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--out", default="eval/results.json")
    ap.add_argument("--randomize-routes", action="store_true")
    args = ap.parse_args()
    if args.episodes < 1:
        ap.error("episodes must be positive")
    import torch
    torch.set_num_threads(1)

    policies = [ApproachFixedPolicy(), ApproachAdaptivePolicy()]
    if os.path.exists(args.model):
        policies.append(DQNPolicy(args.model))
    else:
        print(f"WARNING: model not found at {args.model}, skipping DQN evaluation")

    summary = []
    for policy in policies:
        print(f"\n=== Evaluating {policy.name} ===")
        results = run_policy(policy, args.episode_seconds, args.episodes, args.seed, args.randomize_routes)
        s = summarize(policy.name, results)
        print(json.dumps(s, indent=2))
        summary.append(s)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved comparison to {args.out}")

    if len(summary) >= 2:
        fixed = next((s for s in summary if s["controller"] == "fixed_time"), None)
        dqn = next((s for s in summary if s["controller"] == "dqn"), None)
        if fixed and dqn and fixed["avg_wait_time_s"] > 0:
            improvement = 100 * (fixed["avg_wait_time_s"] - dqn["avg_wait_time_s"]) / fixed["avg_wait_time_s"]
            print(f"\nDQN vs fixed-time wait-time improvement: {improvement:.1f}%")


if __name__ == "__main__":
    main()
