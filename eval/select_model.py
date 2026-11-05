"""Select a checkpoint using validation seeds, keeping final test seeds untouched."""
import argparse
import json
import shutil
from pathlib import Path
import torch
from baselines import DQNPolicy
from evaluate import run_policy, summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--episode-seconds", type=int, default=900)
    parser.add_argument("--seed", type=int, default=9000)
    parser.add_argument("--model-dir", default="models")
    args = parser.parse_args()
    torch.set_num_threads(1)
    directory = Path(args.model_dir)
    models = sorted((directory / "checkpoints").glob("dqn_approach_v3_*_steps.zip"))
    final = directory / "dqn_approach_v3.zip"
    if final.exists():
        models.append(final)
    if not models:
        raise RuntimeError("No four-approach models found")
    scores = []
    for path in models:
        policy = DQNPolicy(str(path))
        results = run_policy(policy, args.episode_seconds, args.episodes, args.seed, True)
        score = summarize("dqn", results)
        score.update(model=str(path), training_steps=int(policy.model.num_timesteps))
        scores.append(score)
        print(path.name, "queue:", score["avg_queue_length_vehicles"],
              "throughput:", score["avg_throughput_vehicles"], flush=True)
    best = min(scores, key=lambda r: (r["total_collision_vehicle_events"],
                                      r["total_teleported_vehicles"],
                                      r["avg_queue_length_vehicles"],
                                      -r["avg_throughput_vehicles"]))
    destination = directory / "dqn_approach_best.zip"
    shutil.copy2(best["model"], destination)
    metadata = dict(selection="zero collisions, then fewer teleports, lower queue, higher throughput",
                    validation_seed=args.seed, episodes=args.episodes,
                    episode_seconds=args.episode_seconds, selected=best, candidates=scores)
    destination.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("Selected:", best["model"], flush=True)


if __name__ == "__main__":
    main()
