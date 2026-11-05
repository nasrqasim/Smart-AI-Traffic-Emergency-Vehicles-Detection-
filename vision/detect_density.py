"""
Vehicle detection + per-lane density estimation demo, matching Section 3.3
"Vehicle Detection & Density Estimation" and Section 1.3.1 "Detection Scope"
of the FYP doc:
  - Real-time per-frame detection/classification of cars, buses, motorcycles,
    trucks using YOLOv8n.
  - Per-lane density estimation via bounding-box-centroid counting inside
    ROI polygons.

This uses YOLOv8n's stock COCO-pretrained weights (fine-tuning on UA-DETRAC
as the doc specifies needs a GPU box and hours of training, out of scope for
this quick pass — see README for how to swap in a fine-tuned checkpoint).
ROI polygons here are illustrative lane regions on the sample video; replace
sample_traffic.mp4 and roi_config.json with your own camera footage and
calibrated lane polygons for real deployment.

Usage:
    python detect_density.py --source traffic_sample.mp4 --out annotated.mp4
    python detect_density.py --source traffic_sample.mp4 --frame 60 --out sample_frame.jpg
"""
import argparse
import json
import os

import cv2
import numpy as np
from ultralytics import YOLO

VEHICLE_CLASS_NAMES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

DEFAULT_ROI_FILE = os.path.join(os.path.dirname(__file__), "roi_lanes.json")


def load_rois(path, frame_w, frame_h):
    if os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
        return {k: np.array(v, dtype=np.int32) for k, v in cfg.items()}
    # fallback: split the frame into left/right halves as two illustrative "lanes"
    return {
        "lane_left": np.array(
            [[0, 0], [frame_w // 2, 0], [frame_w // 2, frame_h], [0, frame_h]],
            dtype=np.int32,
        ),
        "lane_right": np.array(
            [[frame_w // 2, 0], [frame_w, 0], [frame_w, frame_h], [frame_w // 2, frame_h]],
            dtype=np.int32,
        ),
    }


def point_in_poly(pt, poly):
    return cv2.pointPolygonTest(poly, pt, False) >= 0


def process_frame(model, frame, rois, conf=0.2):
    results = model.predict(frame, conf=conf, verbose=False, classes=list(VEHICLE_CLASS_NAMES.keys()))[0]
    lane_counts = {lane: 0 for lane in rois}
    class_counts = {name: 0 for name in VEHICLE_CLASS_NAMES.values()}

    annotated = frame.copy()
    for lane, poly in rois.items():
        cv2.polylines(annotated, [poly], True, (0, 200, 255), 2)

    for box in results.boxes:
        cls_id = int(box.cls[0])
        cls_name = VEHICLE_CLASS_NAMES.get(cls_id, str(cls_id))
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        class_counts[cls_name] = class_counts.get(cls_name, 0) + 1

        for lane, poly in rois.items():
            if point_in_poly((cx, cy), poly):
                lane_counts[lane] += 1
                break

        cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (60, 220, 60), 2)
        cv2.circle(annotated, (int(cx), int(cy)), 3, (0, 0, 255), -1)
        cv2.putText(annotated, cls_name, (int(x1), int(y1) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 220, 60), 1)

    y = 24
    for lane, count in lane_counts.items():
        cv2.putText(annotated, f"{lane}: {count} veh", (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        y += 22

    return annotated, lane_counts, class_counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="traffic_sample.mp4")
    ap.add_argument("--roi", default=DEFAULT_ROI_FILE)
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--out", default="annotated.mp4")
    ap.add_argument("--frame", type=int, default=None,
                     help="if set, process a single frame index and save a still image instead of a video")
    ap.add_argument("--max-frames", type=int, default=150,
                     help="cap on frames processed for the video demo (keeps the run fast)")
    args = ap.parse_args()

    model = YOLO(args.weights)
    cap = cv2.VideoCapture(args.source)
    fps = cap.get(cv2.CAP_PROP_FPS) or 12.5
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    rois = load_rois(args.roi, w, h)

    if args.frame is not None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("could not read requested frame")
        annotated, lane_counts, class_counts = process_frame(model, frame, rois)
        cv2.imwrite(args.out, annotated)
        print(f"Saved {args.out}")
        print("Per-lane density:", lane_counts)
        print("Per-class counts:", class_counts)
        return

    writer = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    frame_idx = 0
    all_lane_counts = []
    while frame_idx < args.max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        annotated, lane_counts, class_counts = process_frame(model, frame, rois)
        writer.write(annotated)
        all_lane_counts.append(lane_counts)
        frame_idx += 1

    cap.release()
    writer.release()
    print(f"Processed {frame_idx} frames -> {args.out}")
    if all_lane_counts:
        avg = {lane: sum(f[lane] for f in all_lane_counts) / len(all_lane_counts)
               for lane in all_lane_counts[0]}
        print("Average per-lane density across clip:", avg)


if __name__ == "__main__":
    main()
