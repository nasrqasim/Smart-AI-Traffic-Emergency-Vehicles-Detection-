import os

target = os.path.join(os.path.dirname(__file__), "..", "rl_env", "traffic_env.py")
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

# Replace self.np_random.integers with a robust call
code = code.replace("self._sumo_seed = int(self.np_random.integers(0, 2**30))",
                    "self._sumo_seed = int(getattr(self.np_random, 'integers', getattr(self.np_random, 'randint'))(0, 2**30))")

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("np_random fix applied!")
