import os

target = os.path.join(os.path.dirname(__file__), "..", "dashboard", "app.py")
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

endpoint_code = '''@app.post("/api/vision/upload_frame")
def upload_browser_frame():
    """Receives a real-time frame from the user's laptop camera/webcam via browser navigator.mediaDevices."""
    import base64
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image")
    if not image_b64:
        return jsonify(error="No image provided"), 400
    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        raw_bytes = base64.b64decode(image_b64)
        res = camera_processor.process_browser_frame(raw_bytes)
        return jsonify(res)
    except Exception as e:
        return jsonify(error=str(e)), 500
'''

if "/api/vision/upload_frame" not in code:
    idx = code.find('@app.get("/api/vision/status")')
    code = code[:idx] + endpoint_code + "\n\n" + code[idx:]
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("Added /api/vision/upload_frame to app.py!")
else:
    print("/api/vision/upload_frame already present")
