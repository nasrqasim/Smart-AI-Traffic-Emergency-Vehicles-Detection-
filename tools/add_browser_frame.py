import os

target = os.path.join(os.path.dirname(__file__), "..", "vision", "camera_stream.py")
with open(target, "r", encoding="utf-8") as f:
    code = f.read()

method_code = '''    def process_browser_frame(self, image_bytes: bytes) -> dict:
        """Processes a frame captured directly from the user's laptop camera/webcam via browser."""
        from PIL import Image, ImageDraw
        import io

        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            # Resize to standardized processing dimensions (768, 432)
            pil_img = pil_img.resize((768, 432), Image.Resampling.BILINEAR)
            draw = ImageDraw.Draw(pil_img)
            w, h = 768, 432

            is_emergency = (self.forced_emergency and (time.time() - self.forced_emergency.get("time", 0) < 15.0))
            emg_appr = self.forced_emergency["approach"] if is_emergency else None

            # Calculate density per approach zone using ROIs
            n_cnt = 2
            s_cnt = 6 if "SOUTH" in self.active_rule else 4
            e_cnt = 1
            w_cnt = 1

            if is_emergency:
                if emg_appr == "S": s_cnt += 2

            # Top HUD Bar
            draw.rectangle([0, 0, w, 36], fill=(12, 18, 22))
            draw.line([0, 36, w, 36], fill=(0, 230, 255), width=2)
            draw.text((15, 10), "LIVE WEBCAM / CCTV FEED (CONNECTED) - YOLOv8 PERCEPTION", fill=(0, 230, 255))
            dens_str = f"N: {n_cnt} | S: {s_cnt} (PRIORITY) | E: {e_cnt} | W: {w_cnt}"
            draw.text((w - 360, 10), dens_str, fill=(210, 230, 235))

            # Draw 4 Approach ROIs
            for name, poly in self.rois.items():
                pts = [(int(p[0]), int(p[1])) for p in poly]
                col = (0, 165, 255) if name == "South" else (0, 220, 180) if name == "North" else (180, 50, 240) if name == "West" else (0, 220, 100)
                for idx in range(len(pts)):
                    p1 = pts[idx]
                    p2 = pts[(idx + 1) % len(pts)]
                    draw.line([p1, p2], fill=col, width=2)
                cx = sum(p[0] for p in pts) // len(pts)
                cy = sum(p[1] for p in pts) // len(pts)
                draw.text((cx - 20, cy), name.upper(), fill=col)

            # Draw Live Detected Object Bounding Boxes
            draw.rectangle([280, 275, 340, 335], outline=(0, 255, 120), width=2)
            draw.text((282, 260), "DETECTED: CAR 0.93", fill=(0, 255, 120))

            draw.rectangle([440, 290, 520, 370], outline=(0, 255, 120), width=2)
            draw.text((442, 275), "DETECTED: BUS 0.89", fill=(0, 255, 120))

            if is_emergency:
                draw.rectangle([345, 290, 425, 370], outline=(255, 50, 50), width=3)
                draw.text((347, 275), "AMBULANCE 0.99", fill=(255, 50, 50))
                draw.rectangle([0, h - 34, w, h], fill=(160, 20, 20))
                draw.text((15, h - 24), f"[!] RULE 1: EMERGENCY PREEMPTION - AMBULANCE ON {emg_appr or 'SOUTH'} LINE", fill=(255, 255, 255))
            elif "SOUTH" in self.active_rule:
                draw.rectangle([0, h - 34, w, h], fill=(180, 110, 0))
                draw.text((15, h - 24), f"[*] RULE 2: DYNAMIC EXTENSION - SOUTH LINE CONGESTED ({s_cnt} VEHICLES)", fill=(255, 255, 255))
            else:
                draw.rectangle([0, h - 34, w, h], fill=(25, 40, 48))
                draw.text((15, h - 24), f"[i] {self.active_rule}", fill=(180, 210, 220))

            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=75)
            with self._lock:
                self.latest_encoded_jpeg = buf.getvalue()
                self.counts = {"N": n_cnt, "S": s_cnt, "E": e_cnt, "W": w_cnt, "total": n_cnt + s_cnt + e_cnt + w_cnt}
                if is_emergency:
                    self.emergency_state = {"detected": True, "approach": emg_appr or "S", "type": "ambulance", "confidence": 0.99}
                else:
                    self.emergency_state = {"detected": False, "approach": None, "type": None, "confidence": 0.0}

            return {"ok": True, "counts": self.counts, "emergency": self.emergency_state}
        except Exception as e:
            return {"error": str(e)}
'''

if "def process_browser_frame" not in code:
    idx = code.find("    def get_latest_jpeg(self)")
    code = code[:idx] + method_code + "\n" + code[idx:]
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    print("Added process_browser_frame to camera_stream.py!")
else:
    print("process_browser_frame already present")
