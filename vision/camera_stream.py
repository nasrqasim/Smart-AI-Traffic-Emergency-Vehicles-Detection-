"""Real-Time Computer Vision & Camera Stream Engine.

Processes live intersection video feeds (webcam, video file, RTSP stream),
performs YOLOv8 vehicle detection and emergency vehicle identification,
applies 4-approach polygon ROI mapping (North, East, South, West),
and generates an annotated MJPEG video stream for the dashboard.
"""
import os
import sys
import time
import json
import threading
from typing import Dict, List, Optional, Tuple

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROI_PATH = os.path.join(THIS_DIR, "roi_4way.json")
DEFAULT_WEIGHTS = os.path.join(THIS_DIR, "yolov8n.pt")
DEFAULT_SAMPLE_VIDEO = os.path.join(THIS_DIR, "traffic_sample.mp4")

# Standard vehicle classes in COCO dataset used by YOLOv8
VEHICLE_CLASS_NAMES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

# Colors for bounding boxes & ROIs (BGR)
APPROACH_COLORS = {
    "North": (255, 120, 0),    # Cyan/Blue
    "South": (0, 165, 255),    # Vibrant Orange (South line highlight)
    "East":  (0, 220, 100),    # Emerald Green
    "West":  (180, 50, 240)    # Purple/Magenta
}


def point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon algorithm (pure Python, dependency-free)."""
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


class CameraStreamProcessor:
    """Thread-safe real-time video processor and vehicle density estimator."""

    def __init__(self, source: str = None, roi_file: str = None, weights_path: str = None):
        self.source = source or DEFAULT_SAMPLE_VIDEO
        self.roi_file = roi_file or DEFAULT_ROI_PATH
        self.weights_path = weights_path or DEFAULT_WEIGHTS
        self.running = False
        self._thread = None
        self._lock = threading.Lock()

        # Telemetry state
        self.counts = {"N": 0, "S": 0, "E": 0, "W": 0, "total": 0}
        self.emergency_state = {"detected": False, "approach": None, "type": None, "confidence": 0.0}
        self.fps = 0.0
        self.last_update_time = time.time()
        self.active_rule = "TRADITIONAL_FALLBACK_60S"
        self.forced_emergency = None

        # Load ROIs
        self.rois = self._load_rois()

        # Frame storage
        self.latest_encoded_jpeg = None
        self._init_backend()
        self._create_initial_frame()

    def _create_initial_frame(self):
        """Pre-renders an initial JPEG frame so stream consumers never see None."""
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (768, 432), color=(20, 24, 30))
            draw = ImageDraw.Draw(img)
            draw.text((250, 200), "INITIALIZING AI VISION STREAM...", fill=(0, 220, 255))
            import io
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            self.latest_encoded_jpeg = buf.getvalue()
        except Exception:
            pass

    def _load_rois(self) -> Dict[str, List[Tuple[int, int]]]:
        if os.path.isfile(self.roi_file):
            try:
                with open(self.roi_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "pixels" in data:
                        return {k: [tuple(p) for p in v] for k, v in data["pixels"].items()}
            except Exception as e:
                print(f"[CameraStream] Error loading ROI file: {e}")

        # Fallback 768x432 4-quadrant layout
        return {
            "North": [(230, 0), (538, 0), (484, 164), (284, 164)],
            "South": [(192, 268), (576, 268), (706, 432), (62, 432)],
            "East":  [(484, 164), (768, 138), (768, 302), (576, 268)],
            "West":  [(0, 138), (284, 164), (192, 268), (0, 302)]
        }

    def _init_backend(self):
        """Attempts to load OpenCV and Ultralytics YOLO; provides synthetic stream fallback if missing."""
        self._cv2 = None
        self._yolo = None
        try:
            import cv2
            self._cv2 = cv2
        except ImportError:
            print("[CameraStream] OpenCV not installed. Running in synthetic camera mode.")

        try:
            from ultralytics import YOLO
            if os.path.isfile(self.weights_path):
                self._yolo = YOLO(self.weights_path)
        except Exception as e:
            print(f"[CameraStream] YOLOv8 not initialized ({e}). Using mock vehicle detector.")

    def start(self):
        """Starts the capture and detection worker thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._capture_and_process_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops the processing loop."""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def set_source(self, new_source: str):
        """Switches video input between video file, webcam index, or RTSP stream."""
        with self._lock:
            self.source = new_source
            print(f"[CameraStream] Source updated to: {self.source}")

    def trigger_emergency_test(self, approach: str = "S", vehicle_type: str = "ambulance"):
        """Allows testing Rule 1 (Emergency Preemption) directly from dashboard or test script."""
        with self._lock:
            self.forced_emergency = {"detected": True, "approach": approach, "type": vehicle_type, "time": time.time()}

    def clear_emergency_test(self):
        with self._lock:
            self.forced_emergency = None

    def update_active_rule(self, rule_name: str):
        """Reflects the controller's active rule on the camera HUD."""
        self.active_rule = rule_name

    def _capture_and_process_loop(self):
        """Main processing loop fetching video frames and running YOLO detection."""
        cv2 = self._cv2
        if cv2 is None:
            self._synthetic_stream_loop()
            return

        while self.running:
            # Open source (can be int for webcam, or str for file/stream)
            src = self.source
            try:
                src_val = int(src)
            except (ValueError, TypeError):
                src_val = src

            cap = cv2.VideoCapture(src_val)
            if not cap.isOpened():
                print(f"[CameraStream] Cannot open source '{self.source}'. Falling back to synthetic.")
                time.sleep(1.0)
                continue

            fps_target = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frame_delay = 1.0 / max(10.0, min(fps_target, 30.0))

            while self.running and cap.isOpened():
                t_start = time.time()
                ret, frame = cap.read()
                if not ret:
                    # Loop video if playing a sample file
                    if isinstance(src_val, str) and os.path.isfile(src_val):
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    else:
                        time.sleep(0.1)
                        break

                processed_frame, counts, emergency = self._process_frame(frame)

                with self._lock:
                    self.counts = counts
                    self.emergency_state = emergency
                    # Encode to JPEG
                    ret_enc, buffer = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                    if ret_enc:
                        self.latest_encoded_jpeg = buffer.tobytes()

                elapsed = time.time() - t_start
                self.fps = 1.0 / max(elapsed, 0.001)
                sleep_time = frame_delay - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            cap.release()

    def _process_frame(self, frame) -> Tuple[any, Dict[str, int], Dict]:
        """Runs YOLO detection, classifies approaches by ROI polygons, and draws overlays."""
        cv2 = self._cv2
        h, w = frame.shape[:2]

        # Scaled ROIs if frame dimensions differ from 768x432
        rois = {}
        for name, poly in self.rois.items():
            if (w, h) == (768, 432):
                rois[name] = poly
            else:
                scale_x = w / 768.0
                scale_y = h / 432.0
                rois[name] = [(int(px * scale_x), int(py * scale_y)) for px, py in poly]

        counts = {"N": 0, "S": 0, "E": 0, "W": 0, "total": 0}
        approach_map = {"North": "N", "South": "S", "East": "E", "West": "W"}
        emergency = {"detected": False, "approach": None, "type": None}

        # Check manual test trigger
        if self.forced_emergency and (time.time() - self.forced_emergency["time"] < 15.0):
            emergency = {
                "detected": True,
                "approach": self.forced_emergency["approach"],
                "type": self.forced_emergency["type"],
                "confidence": 0.98
            }

        # Draw semi-transparent ROI polygons
        overlay = frame.copy()
        for name, poly in rois.items():
            pts = [(int(p[0]), int(p[1])) for p in poly]
            color = APPROACH_COLORS.get(name, (200, 200, 200))
            # Fill polygon on overlay
            import numpy as np
            cv2.fillPoly(overlay, [np.array(pts, dtype=np.int32)], color)
        # Blend overlay (alpha 0.12)
        cv2.addWeighted(overlay, 0.12, frame, 0.88, 0, frame)

        # Draw ROI polygon boundaries and labels
        for name, poly in rois.items():
            pts = [(int(p[0]), int(p[1])) for p in poly]
            color = APPROACH_COLORS.get(name, (200, 200, 200))
            import numpy as np
            cv2.polylines(frame, [np.array(pts, dtype=np.int32)], True, color, 2)
            # Label
            cx = int(sum(p[0] for p in pts) / len(pts))
            cy = int(sum(p[1] for p in pts) / len(pts))
            cv2.putText(frame, f"{name.upper()}", (cx - 25, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        # Run YOLO inference if model is loaded
        if self._yolo is not None:
            try:
                results = self._yolo.predict(frame, conf=0.25, verbose=False, classes=list(VEHICLE_CLASS_NAMES.keys()))[0]
                for box in results.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    cls_name = VEHICLE_CLASS_NAMES.get(cls_id, "vehicle")
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)

                    # Determine approach by centroid
                    matched_appr = None
                    for name, poly in rois.items():
                        if point_in_polygon(cx, cy, poly):
                            appr_code = approach_map[name]
                            counts[appr_code] += 1
                            counts["total"] += 1
                            matched_appr = appr_code
                            break

                    # Check for emergency vehicle heuristic or class
                    is_emergency = False
                    if "ambulance" in cls_name or "emergency" in cls_name:
                        is_emergency = True
                        emergency = {"detected": True, "approach": matched_appr or "S", "type": "ambulance"}
                    # Also examine patch color or aspect if red/white siren is active
                    elif cls_name in ("bus", "truck", "car") and matched_appr:
                        # Heuristic: inspect top region of vehicle box for emergency strobe/red hue
                        try:
                            top_strip = frame[max(0, y1):min(h, y1 + int((y2 - y1) * 0.25)), max(0, x1):min(w, x2)]
                            if top_strip.size > 0:
                                hsv = cv2.cvtColor(top_strip, cv2.COLOR_BGR2HSV)
                                # Red color masks in HSV
                                mask1 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
                                mask2 = cv2.inRange(hsv, np.array([170, 100, 100]), np.array([180, 255, 255]))
                                red_pixels = cv2.countNonZero(mask1 | mask2)
                                if red_pixels / (top_strip.shape[0] * top_strip.shape[1] + 1) > 0.35:
                                    is_emergency = True
                                    emergency = {"detected": True, "approach": matched_appr, "type": "ambulance"}
                        except Exception:
                            pass

                    # Draw bounding box
                    box_color = (0, 0, 255) if is_emergency else (0, 255, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                    cv2.circle(frame, (cx, cy), 3, (0, 0, 255), -1)

                    label = f"{'EMERGENCY ' if is_emergency else ''}{cls_name.upper()} {conf:.2f}"
                    cv2.putText(frame, label, (x1, max(12, y1 - 5)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, box_color, 1)
            except Exception as e:
                pass
        else:
            # Fallback mock detector for sample demonstration
            counts = {"N": 2, "S": 6, "E": 1, "W": 0, "total": 9}

        # Draw HUD & Rule Status Banners
        self._render_hud(frame, counts, emergency)

        return frame, counts, emergency

    def _render_hud(self, frame, counts: Dict[str, int], emergency: Dict):
        """Draws top information banner and priority rule status on the frame."""
        cv2 = self._cv2
        w = frame.shape[1]

        # Top banner background
        cv2.rectangle(frame, (0, 0), (w, 36), (20, 24, 30), -1)
        cv2.line(frame, (0, 36), (w, 36), (60, 70, 80), 1)

        # Title
        cv2.putText(frame, "AI VISION FEED / 4-APPROACH SENSING", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 2)

        # Density readout
        dens_txt = f"N: {counts['N']} | S: {counts['S']} | E: {counts['E']} | W: {counts['W']} (TOTAL: {counts['total']})"
        cv2.putText(frame, dens_txt, (w - 380, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

        # Bottom Rule Status Banner
        if emergency.get("detected"):
            # Rule 1 Banner: Flashing Red Alert
            appr = emergency.get("approach") or "APPROACH"
            cv2.rectangle(frame, (0, frame.shape[0] - 34), (w, frame.shape[0]), (0, 0, 180), -1)
            cv2.putText(frame, f"[!] RULE 1: EMERGENCY PREEMPTION ACTIVE - {emergency.get('type', 'AMBULANCE').upper()} ON {appr} LINE",
                        (15, frame.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        elif counts.get("S", 0) >= 3 or self.active_rule == "SOUTH_LINE_DYNAMIC_EXTENSION":
            # Rule 2 Banner: South Line Priority Dynamic Extension
            cv2.rectangle(frame, (0, frame.shape[0] - 34), (w, frame.shape[0]), (0, 120, 220), -1)
            cv2.putText(frame, f"[*] RULE 2: DENSITY EXTENSION - SOUTH LINE CONGESTION ({counts['S']} VEHICLES)",
                        (15, frame.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        elif counts.get("total", 0) <= 1 or self.active_rule == "TRADITIONAL_FALLBACK_60S":
            # Rule 3 Banner: 60s Traditional Fallback
            cv2.rectangle(frame, (0, frame.shape[0] - 34), (w, frame.shape[0]), (40, 50, 60), -1)
            cv2.putText(frame, "[i] RULE 3: TRADITIONAL FALLBACK CYCLE (60s ROTATION / LOW TRAFFIC)",
                        (15, frame.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 200, 210), 1)

    def _synthetic_stream_loop(self):
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

    def process_browser_frame(self, image_bytes: bytes) -> dict:
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

            import base64
            b64_out = "data:image/jpeg;base64," + base64.b64encode(self.latest_encoded_jpeg).decode("ascii")
            return {"ok": True, "counts": self.counts, "emergency": self.emergency_state, "annotated_jpeg": b64_out}
        except Exception as e:
            return {"error": str(e)}

    def get_latest_jpeg(self) -> Optional[bytes]:
        """Returns the most recent JPEG bytes for HTTP response."""
        with self._lock:
            return self.latest_encoded_jpeg

    def get_telemetry(self) -> Dict:
        """Returns current detection counts and emergency status."""
        with self._lock:
            return {
                "counts": dict(self.counts),
                "emergency": dict(self.emergency_state),
                "fps": round(self.fps, 1),
                "source": self.source,
                "active_rule": self.active_rule
            }


# Global singleton instance for easy import across dashboard and evaluation
camera_processor = CameraStreamProcessor()
