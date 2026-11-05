import os

target = os.path.join(os.path.dirname(__file__), "..", "vision", "camera_stream.py")
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

old_ret = 'return {"ok": True, "counts": self.counts, "emergency": self.emergency_state}'
new_ret = '''import base64
            b64_out = "data:image/jpeg;base64," + base64.b64encode(self.latest_encoded_jpeg).decode("ascii")
            return {"ok": True, "counts": self.counts, "emergency": self.emergency_state, "annotated_jpeg": b64_out}'''

if old_ret in code:
    code = code.replace(old_ret, new_ret)
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("process_browser_frame updated to include annotated_jpeg!")
else:
    print("old_ret not found")
