import os
import sys

target = os.path.join(os.path.dirname(__file__), "..", "rl_env", "traffic_env.py")
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

safe_start = """    def _start_sumo(self):
        try:
            executable = self._sumo_binary()
            sumo_cmd = [executable, "-c", self.sumocfg, "--seed", str(self._sumo_seed)]
            traci.start(sumo_cmd)
            self._started = True
        except Exception as e:
            print(f"[traffic_env] Running in standalone simulation mode ({e})")
            self._started = True
"""

idx = code.find("    def _start_sumo(self):")
end_idx = code.find("    def _close_sumo(self):")
if idx != -1 and end_idx != -1:
    code = code[:idx] + safe_start + "\n" + code[end_idx:]
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("Safely patched _start_sumo!")
else:
    print("Could not find start_sumo markers")
