#!/usr/bin/env python3
"""Read JSON stdin, count unique pedestrians in videos, and create an exact XLSX."""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from openpyxl import Workbook, load_workbook

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm", ".mpeg", ".mpg"}
PERSON = 0
VEHICLE_CLASSES = {1, 2, 3, 5, 7}  # bicycle, car, motorcycle, bus, truck in COCO


def die(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(2)


def box_metrics(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    aa = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    return inter / aa


def expanded_contains(box, point, factor=0.18):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    return (x1 - factor * w <= point[0] <= x2 + factor * w and
            y1 - factor * h <= point[1] <= y2 + factor * h)


def vehicle_associated(person_box, other_boxes):
    """True only where body position and overlap indicate riding/occupancy."""
    x1, y1, x2, y2 = person_box
    center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    lower_center = (center[0], y1 + 0.72 * (y2 - y1))
    for cls, vehicle_box in other_boxes:
        overlap = box_metrics(person_box, vehicle_box)
        if cls in (1, 3):
            # A rider normally overlaps the cycle/motorcycle at the lower body.
            if overlap >= 0.14 and expanded_contains(vehicle_box, lower_center, 0.30):
                return True
        else:
            # Occupants are generally centered inside a vehicle detection, unlike passersby.
            if overlap >= 0.20 and expanded_contains(vehicle_box, center, 0.08):
                return True
    return False


def center_and_scale(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0), math.hypot(x2 - x1, y2 - y1)


def track_summary(track):
    obs = track["obs"]
    first, last = obs[0], obs[-1]
    result = {
        "id": track["id"], "start_frame": first["frame"], "end_frame": last["frame"],
        "start_time_s": first["time_s"], "end_time_s": last["time_s"],
        "detections": len(obs), "vehicle_associated_detections": track["vehicle_hits"],
        "start_box": [round(x, 2) for x in first["box"]],
        "end_box": [round(x, 2) for x in last["box"]],
    }
    # Sustained evidence is required; a short track is rejected only if all observations agree.
    result["pedestrian"] = not (track["vehicle_hits"] >= 2 and
                                track["vehicle_hits"] / len(obs) >= 0.50)
    return result


def compatible_join(a, b, diagonal):
    """Conservative, forward-time endpoint test for fragmented track IDs."""
    if b["start_time_s"] <= a["end_time_s"]:
        return False
    gap = b["start_time_s"] - a["end_time_s"]
    if gap > 2.0:
        return False
    ac, ascale = center_and_scale(a["end_box"])
    bc, bscale = center_and_scale(b["start_box"])
    dist = math.dist(ac, bc)
    # The geometry is normalized to image size and subject size, not fixed pixels.
    gate = max(0.035 * diagonal, 1.6 * max(ascale, bscale)) + 0.065 * diagonal * gap
    return dist <= gate


def stitch(summaries, diagonal):
    eligible = [s for s in summaries if s["pedestrian"]]
    eligible.sort(key=lambda x: (x["end_time_s"], x["id"]))
    parent = {s["id"]: s["id"] for s in eligible}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # A component has one current terminal tracklet. Greedy chronological linking prevents
    # a later identity from joining multiple simultaneously plausible pedestrians.
    terminal = {}
    joins = []
    for candidate in sorted(eligible, key=lambda x: (x["start_time_s"], x["id"])):
        choices = []
        for root, prior in terminal.items():
            if compatible_join(prior, candidate, diagonal):
                pc, _ = center_and_scale(prior["end_box"])
                cc, _ = center_and_scale(candidate["start_box"])
                choices.append((math.dist(pc, cc), root, prior))
        if choices:
            _, root, prior = min(choices, key=lambda row: row[0])
            parent[candidate["id"]] = root
            joins.append({"from_id": prior["id"], "to_id": candidate["id"]})
            terminal[root] = candidate
        else:
            terminal[candidate["id"]] = candidate
    components = defaultdict(list)
    for item in eligible:
        components[find(item["id"])].append(item["id"])
    return sorted([sorted(v) for v in components.values()], key=lambda x: (x[0], len(x))), joins


def analyze_video(path, model, config):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError("cannot open video: " + str(path))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not math.isfinite(fps) or fps <= 0:
        fps = 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    diagonal = math.hypot(width, height)
    if diagonal <= 0:
        cap.release()
        raise RuntimeError("invalid video geometry: " + str(path))

    tracks = {}
    frame = 0
    processed = 0
    stride = config["stride"]
    try:
        while True:
            ok, image = cap.read()
            if not ok:
                break
            if frame % stride:
                frame += 1
                continue
            result = model.track(image, persist=True, tracker=config["tracker"],
                                 conf=config["confidence"], iou=0.55, verbose=False)[0]
            processed += 1
            boxes = result.boxes
            if boxes is not None and boxes.xyxy is not None and len(boxes) > 0:
                xyxy = boxes.xyxy.cpu().numpy()
                classes = boxes.cls.cpu().numpy().astype(int)
                ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None
                others = [(int(c), [float(v) for v in xyxy[i]])
                          for i, c in enumerate(classes) if int(c) in VEHICLE_CLASSES]
                if ids is not None:
                    for i, c in enumerate(classes):
                        if int(c) != PERSON:
                            continue
                        tid = int(ids[i])
                        box = [float(v) for v in xyxy[i]]
                        entry = tracks.setdefault(tid, {"id": tid, "obs": [], "vehicle_hits": 0})
                        hit = vehicle_associated(box, others)
                        entry["vehicle_hits"] += int(hit)
                        entry["obs"].append({"frame": frame, "time_s": frame / fps,
                                             "box": box, "vehicle_associated": hit})
            frame += 1
    finally:
        cap.release()

    summaries = [track_summary(t) for _, t in sorted(tracks.items()) if t["obs"]]
    components, joins = stitch(summaries, diagonal)
    return {
        "fps": fps, "width": width, "height": height, "decoded_frames": frame,
        "processed_frames": processed, "tracklets": summaries, "joins": joins,
        "components": components, "count": len(components),
    }


def write_workbook(output_path, rows):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(["filename", "number"])
    for filename, count in rows:
        ws.append([filename, int(count)])
    wb.save(output_path)


def validate_workbook(output_path, expected_names):
    wb = load_workbook(output_path, data_only=False)
    if wb.sheetnames != ["results"]:
        raise ValueError("workbook must contain exactly one worksheet named results")
    ws = wb["results"]
    if ws.max_row != len(expected_names) + 1 or ws.max_column != 2:
        raise ValueError("workbook contains extra or missing cells")
    if [ws.cell(1, c).value for c in (1, 2)] != ["filename", "number"]:
        raise ValueError("headers are not exactly filename, number")
    names = []
    for row in range(2, ws.max_row + 1):
        name, count = ws.cell(row, 1).value, ws.cell(row, 2).value
        if not isinstance(name, str) or type(count) is not int or count < 0:
            raise ValueError("data rows require a string filename and nonnegative integer number")
        names.append(name)
    if names != expected_names or names != sorted(names):
        raise ValueError("filenames do not exactly match sorted input videos")
    return True


def main():
    try:
        config = json.load(sys.stdin)
    except Exception as exc:
        die("stdin must contain one JSON object: " + str(exc))
    if not isinstance(config, dict):
        die("configuration must be a JSON object")
    if not config.get("source_dir") or not config.get("output_path"):
        die("source_dir and output_path are required")
    source = Path(config["source_dir"])
    output = Path(config["output_path"])
    if not source.is_dir():
        die("source_dir is not a directory: " + str(source))
    try:
        stride = int(config.get("stride", 1))
        confidence = float(config.get("confidence", 0.22))
    except (TypeError, ValueError):
        die("stride must be an integer and confidence a number")
    if stride < 1 or not 0 < confidence < 1:
        die("stride must be >= 1 and confidence must be between 0 and 1")
    config = {"stride": stride, "confidence": confidence,
              "weights": str(config.get("weights", "yolo11x.pt")),
              "tracker": str(config.get("tracker", "bytetrack.yaml"))}
    videos = sorted([p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS],
                    key=lambda p: p.relative_to(source).as_posix())
    if not videos:
        die("no supported video files found under " + str(source))
    try:
        from ultralytics import YOLO
        model = YOLO(config["weights"])
        reports = {}
        rows = []
        for video in videos:
            name = video.relative_to(source).as_posix()
            report = analyze_video(video, model, config)
            reports[name] = report
            rows.append((name, report["count"]))
        write_workbook(output, rows)
        valid = validate_workbook(output, [name for name, _ in rows])
        review = config.get("review_json")
        if review:
            review_path = Path(review)
            review_path.parent.mkdir(parents=True, exist_ok=True)
            review_path.write_text(json.dumps({"videos": reports}, indent=2, sort_keys=True), encoding="utf-8")
        compact = {name: {"count": item["count"], "raw_tracklets": len(item["tracklets"]),
                          "stitches": len(item["joins"]), "rejected_tracklets": sum(not x["pedestrian"] for x in item["tracklets"])}
                   for name, item in reports.items()}
        print(json.dumps({"ok": True, "output_path": str(output), "workbook_valid": valid,
                          "videos": compact}, sort_keys=True))
    except Exception as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
