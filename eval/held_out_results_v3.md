# Held-out simulation benchmark

5 matched scenarios per controller; 900 simulated seconds each.

| Controller | Queue (veh) | Completed wait (s) | Completed trips | Active at end | Pending at end | Collision events | Teleported vehicles |
|---|---:|---:|---:|---:|---:|---:|---:|
| Fixed cycle | 87.52 | 125.7 | 341.0 | 248.0 | 74.4 | 0 | 0 |
| Density adaptive | 83.89 | 114.26 | 363.8 | 242.2 | 57.4 | 0 | 0 |
| Trained DQN | 86.8 | 117.12 | 345.2 | 238.4 | 79.8 | 0 | 0 |

Means describe these simulation scenarios; they are not real-world accuracy guarantees.
Completed-trip wait excludes unfinished vehicles. Assess queues, throughput and backlog together.
Collision counts are vehicle events reported by SUMO, not independent crash counts.
The controller with the lowest queue and highest completed throughput is preferred for this scenario set.
Legacy two-axis results are not comparable with these exclusive four-approach results.
