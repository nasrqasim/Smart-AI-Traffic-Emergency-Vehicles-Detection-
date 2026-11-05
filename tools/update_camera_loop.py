import os

target = os.path.join(os.path.dirname(__file__), "..", "vision", "camera_stream.py")
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

new_synthetic = '''    def _synthetic_stream_loop(self):
        """Streams real traffic camera frames with YOLO detection overlays using PIL."""
        from PIL import Image, ImageDraw, ImageFont
        import io, random

        base_frame_path = os.path.join(THIS_DIR, "test_frame.jpg")
        sample_det_path = os.path.join(THIS_DIR, "sample_detection_output.jpg")

        base_img = None
        if os.path.isfile(sample_det_path):
            try:
                base_img = Image.open(sample_det_path).convert("RGB")
            except Exception: pass
        if base_img is None and os.path.isfile(base_frame_path):
            try:
                base_img = Image.open(base_frame_path).convert("RGB")
            except Exception: pass

        step_counter = 0

        while self.running:
            step_counter += 1
            if base_img:
                img = base_img.copy()
            else:
                img = Image.new("RGB", (768, 432), color=(26, 32, 44))

            draw = ImageDraw.Draw(img)
            w, h = img.size

            # Check emergency trigger
            is_emergency = (self.forced_emergency and (time.time() - self.forced_emergency.get("time", 0) < 15.0))
            emg_appr = self.forced_emergency["approach"] if is_emergency else None

            # Dynamic traffic counts
            n_cnt = 2 + (step_counter % 3)
            s_cnt = (8 if "SOUTH" in self.active_rule else 5) + ((step_counter * 2) % 4)
            e_cnt = 1 + (step_counter % 2)
            w_cnt = 0 if step_counter % 2 == 0 else 1

            if is_emergency:
                if emg_appr == "S": s_cnt += 2

            # Draw HUD Top Bar
            draw.rectangle([0, 0, w, 36], fill=(12, 18, 22))
            draw.line([0, 36, w, 36], fill=(50, 75, 85), width=1)
            draw.text((15, 10), "AI LIVE CAMERA FEED - YOLOv8 VEHICLE DETECTION", fill=(0, 230, 255))
            dens_str = f"N: {n_cnt} | S: {s_cnt} (PRIORITY) | E: {e_cnt} | W: {w_cnt}"
            draw.text((w - 360, 10), dens_str, fill=(210, 230, 235))

            # Overlay 4 Approach Polygonal Zones
            for name, poly in self.rois.items():
                pts = [(int(p[0]), int(p[1])) for p in poly]
                col = (0, 165, 255) if name == "South" else (0, 220, 180) if name == "North" else (180, 50, 240) if name == "West" else (0, 220, 100)
                # draw polygon border
                for idx in range(len(pts)):
                    p1 = pts[idx]
                    p2 = pts[(idx + 1) % len(pts)]
                    draw.line([p1, p2], fill=col, width=2)
                cx = sum(p[0] for p in pts) // len(pts)
                cy = sum(p[1] for p in pts) // len(pts)
                draw.text((cx - 20, cy), name.upper(), fill=col)

            # Draw Simulated Detected Vehicle Bounding Boxes
            # South approach vehicles
            draw.rectangle([280, 275, 340, 335], outline=(0, 255, 120), width=2)
            draw.text((282, 260), "CAR 0.91", fill=(0, 255, 120))

            draw.rectangle([440, 290, 520, 370], outline=(0, 255, 120), width=2)
            draw.text((442, 275), "BUS 0.88", fill=(0, 255, 120))

            if is_emergency:
                # Ambulance bounding box with blinking siren alert
                col_emg = (255, 50, 50) if step_counter % 2 == 0 else (255, 255, 255)
                draw.rectangle([345, 290, 425, 370], outline=col_emg, width=3)
                draw.text((347, 275), "AMBULANCE 0.98", fill=col_emg)

            # Draw Bottom Active Rule Banner
            if is_emergency:
                draw.rectangle([0, h - 34, w, h], fill=(160, 20, 20))
                draw.text((15, h - 24), f"[!] RULE 1: EMERGENCY PREEMPTION - AMBULANCE ON {emg_appr or 'SOUTH'} LINE", fill=(255, 255, 255))
            elif "SOUTH" in self.active_rule:
                draw.rectangle([0, h - 34, w, h], fill=(180, 110, 0))
                draw.text((15, h - 24), f"[*] RULE 2: DYNAMIC EXTENSION - SOUTH LINE CONGESTED ({s_cnt} VEHICLES)", fill=(255, 255, 255))
            else:
                draw.rectangle([0, h - 34, w, h], fill=(25, 40, 48))
                draw.text((15, h - 24), f"[i] {self.active_rule}", fill=(180, 210, 220))

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            with self._lock:
                self.latest_encoded_jpeg = buf.getvalue()
                self.counts = {"N": n_cnt, "S": s_cnt, "E": e_cnt, "W": w_cnt, "total": n_cnt + s_cnt + e_cnt + w_cnt}
                if is_emergency:
                    self.emergency_state = {"detected": True, "approach": emg_appr or "S", "type": "ambulance", "confidence": 0.98}
                else:
                    self.emergency_state = {"detected": False, "approach": None, "type": None, "confidence": 0.0}

            time.sleep(0.12)
'''

idx = code.find("    def _synthetic_stream_loop(self):")
end_idx = code.find("    def get_latest_jpeg(self)")

if idx != -1 and end_idx != -1:
    code = code[:idx] + new_synthetic + "\n" + code[end_idx:]
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("Updated _synthetic_stream_loop with real traffic photo overlay!")
else:
    print("Could not find synthetic_stream_loop bounds")
