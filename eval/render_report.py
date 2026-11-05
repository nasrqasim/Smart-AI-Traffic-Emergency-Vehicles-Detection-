"""Render measured controller results as a shareable chart and Markdown report."""
import argparse
import json
import os
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="eval/held_out_results_v3.json")
    args = parser.parse_args()
    source = Path(args.input)
    rows = json.loads(source.read_text(encoding="utf-8"))
    labels = {"fixed_time": "Fixed cycle", "actuated": "Density adaptive", "dqn": "Trained DQN"}
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "traffic-fyp-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), facecolor="#0b1114")
    metrics = [("avg_queue_length_vehicles", "Average incoming queue", "vehicles · lower is better"),
               ("avg_wait_time_s", "Completed-trip wait", "seconds · lower is better"),
               ("avg_throughput_vehicles", "Completed trips", "vehicles · higher is better")]
    colors = ["#d5b985", "#a5f3ce", "#88bbdf"]
    for ax, (key, title, unit) in zip(axes, metrics):
        ax.set_facecolor("#0b1114")
        values = [r[key] for r in rows]
        bars = ax.barh([labels[r["controller"]] for r in rows], values, color=colors, height=.55)
        ax.invert_yaxis()
        ax.set_xlim(0, max(values) * 1.25 if any(values) else 1)
        ax.set_title(title, color="#edf3f2", pad=18, loc="left")
        ax.set_xlabel(unit, color="#819398")
        ax.tick_params(colors="#b8cbcd", length=0)
        for bar, value in zip(bars, values):
            ax.text(value + max(values) * .025, bar.get_y() + bar.get_height()/2,
                    f"{value:.1f}", va="center", color="#edf3f2")
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.suptitle("Smart traffic signal · held-out simulation benchmark", color="#edf3f2", fontsize=16)
    first = rows[0]
    horizon = first["episode_results"][0]["sim_time_s"]
    fig.text(.5, .015, f"{first['episodes']} scenarios/controller · {horizon}s each · matched demand and seeds · completed-trip wait excludes unfinished vehicles", ha="center", color="#819398", fontsize=8)
    fig.tight_layout(rect=(0, .05, 1, .91), w_pad=2)
    fig.savefig(source.with_suffix(".png"), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    lines = ["# Held-out simulation benchmark", "",
             f"{first['episodes']} matched scenarios per controller; {horizon} simulated seconds each.", "",
             "| Controller | Queue (veh) | Completed wait (s) | Completed trips | Active at end | Pending at end | Collision events | Teleported vehicles |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in [labels[row["controller"]], row["avg_queue_length_vehicles"],
                     row["avg_wait_time_s"], row["avg_throughput_vehicles"], row["avg_active_at_end"],
                     row["avg_pending_at_end"], row["total_collision_vehicle_events"], row["total_teleported_vehicles"]]) + " |")
    lines += ["", "Means describe these simulation scenarios; they are not real-world accuracy guarantees.",
              "Completed-trip wait excludes unfinished vehicles. Assess queues, throughput and backlog together.",
              "Collision counts are vehicle events reported by SUMO, not independent crash counts.",
              "The controller with the lowest queue and highest completed throughput is preferred for this scenario set.",
              "Legacy two-axis results are not comparable with these exclusive four-approach results.", ""]
    source.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print(source.with_suffix(".md"))


if __name__ == "__main__":
    main()
