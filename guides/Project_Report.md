# Project report
## AI Smart Traffic Signal Control
This final-year project simulates an intelligent four-way traffic intersection. A trained AI controller selects which road receives green and for how long. A browser dashboard displays actual simulated vehicles, signal states, queues, waiting time and completed trips. It runs locally without cameras, traffic hardware or a GPU.

## Techniques used
- Traffic simulation: SUMO models roads, lane changes, turns and vehicle movement. TraCI connects Python to the simulator; libsumo accelerates offline training.
- Reinforcement learning: a Deep Q-Network (DQN), implemented with Stable-Baselines3 and PyTorch, learns from a negative time-averaged queue reward. Its network has two 64-unit hidden layers, experience replay, a target network and epsilon-greedy exploration. VecNormalize scales training rewards.
- State and actions: 18 inputs describe eight lane densities, the active approach, elapsed green, emergency presence and four red ages. The 16 actions combine four approaches with 10, 20, 30 or 45 seconds of green.
- Signal safeguards: one approach is green at a time. Changes use 3 seconds of yellow and 2 seconds of all red. Waiting approaches receive priority through fairness rules. Emergency vehicles within 200 m receive priority while clearance is preserved.
- Web monitoring: Flask and Socket.IO expose live state and queued controls. The current browser UI polls the state API and draws interpolated vehicle positions on an HTML canvas, with Midnight/Daylight and fullscreen views.
- Optional computer vision: a separate YOLOv8n/OpenCV demo detects vehicles in video. It uses pretrained weights and is not the sensor source for the SUMO controller.

## What has been measured
Training completed 12,000 decisions with randomized route demand. Validation selected the 10,000-decision checkpoint. Final testing used five separate, matched 900-second scenarios per controller.

| Controller | Mean queue (vehicles) | Completed-trip wait (s) | Completed trips |
|---|---:|---:|---:|
| Fixed cycle | 87.52 | 125.70 | 341.0 |
| Density adaptive | 83.89 | 114.26 | 363.8 |
| Trained DQN | 86.80 | 117.12 | 345.2 |

DQN reduced completed-trip wait by 6.8% against fixed timing, but the density-adaptive baseline performed better overall. All three controllers recorded zero collision vehicle events and zero teleports in these tests. Completed-trip wait excludes unfinished trips; these results are simulation evidence, not real-world accuracy or safety guarantees. Ten real-SUMO integration tests cover signal clearance, exclusivity, emergency priority, fairness and reset behavior.

## Current scope
The dashboard defaults to trained DQN and automatic traffic. Existing checkpoints can run immediately; retraining is optional. The Colab notebook supports longer experiments. Real-camera accuracy requires labeled test data and further detector evaluation. Hardware deployment is outside this simulation build.
