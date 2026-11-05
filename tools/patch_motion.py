import os

# Update app.js so that speed dropdown reflects d.speed smoothly
target_js = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static", "app.js")
with open(target_js, "r", encoding="utf-8") as f:
    js = f.read()

old_s = "$('speed').value = String(d.speed);"
new_s = "if (document.activeElement !== $('speed')) { $('speed').value = String(d.speed); }"

if old_s in js:
    js = js.replace(old_s, new_s)
    with open(target_js, "w", encoding="utf-8") as f:
        f.write(js)
    print("Updated app.js speed sync!")
else:
    print("old_s not found")

# Update MockTraci in traffic_env.py so vehicles advance at realistic, natural speed along lanes
target_env = os.path.join(os.path.dirname(__file__), "..", "rl_env", "traffic_env.py")
with open(target_env, "r", encoding="utf-8") as f:
    env_code = f.read()

# Let's inspect getPosition in MockTraci vehicle
old_pos = """            @staticmethod
            def getPosition(vid):
                # 4-way intersection map layout centered at 250, 250
                routes = [
                    (246.8, random.uniform(10, 490), 0),
                    (253.2, random.uniform(10, 490), 180),
                    (random.uniform(10, 490), 246.8, 90),
                    (random.uniform(10, 490), 253.2, 270)
                ]
                r = routes[hash(vid) % len(routes)]
                return (r[0], r[1])"""

new_pos = """            _positions = {}
            @classmethod
            def getPosition(cls, vid):
                import time
                # Smooth continuous motion along approaches (North-South: x=246.8 or 253.2, East-West: y=246.8 or 253.2)
                t = time.time() * 8.0  # gentle, realistic speed
                h = abs(hash(vid))
                route_id = h % 4
                offset = (h * 37) % 500
                if route_id == 0:
                    # Moving South (from y=500 down towards 0)
                    y = (500 - (t + offset) % 500)
                    return (246.8, y)
                elif route_id == 1:
                    # Moving North (from y=0 up towards 500)
                    y = ((t + offset) % 500)
                    return (253.2, y)
                elif route_id == 2:
                    # Moving East (from x=0 to 500)
                    x = ((t + offset) % 500)
                    return (x, 246.8)
                else:
                    # Moving West (from x=500 to 0)
                    x = (500 - (t + offset) % 500)
                    return (x, 253.2)"""

if old_pos in env_code:
    env_code = env_code.replace(old_pos, new_pos)
    with open(target_env, "w", encoding="utf-8") as f:
        f.write(env_code)
    print("Updated vehicle motion to smooth, realistic speed!")
else:
    print("old_pos not found in traffic_env.py")
