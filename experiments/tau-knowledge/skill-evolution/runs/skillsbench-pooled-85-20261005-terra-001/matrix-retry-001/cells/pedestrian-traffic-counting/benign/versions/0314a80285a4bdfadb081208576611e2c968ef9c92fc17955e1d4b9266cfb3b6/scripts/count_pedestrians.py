#!/usr/bin/env python3
"""Track and count unique on-foot pedestrians, then write an exact XLSX table.

JSON stdin schema is documented in ../SKILL.md. JSON stdout is a run report.
"""
import json
import math
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


def fail(message):
    raise ValueError(message)


def load_request():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"stdin must be one JSON object: {exc}")
    if not isinstance(request, dict):
        fail("stdin JSON must be an object")
    return request


def video_files(video_dir):
    extensions = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
    found = sorted(
        (p for p in video_dir.rglob("*") if p.is_file() and p.suffix.lower() in extensions),
        key=lambda p: (p.name.casefold(), p.as_posix().casefold()),
    )
    names = [p.name for p in found]
    if len(names) != len(set(names)):
        fail("recursive video input has duplicate basenames; filename output would be ambiguous")
    if not found:
        fail(f"no supported video files found under {video_dir}")
    return found


def area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def intersection_area(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def centre(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def bicycle_relation(person, bicycle):
    """Whether geometry is consistent with this detected person riding this bike.

    This is intentionally stronger than generic proximity so that a pedestrian
    passing a parked bicycle is normally retained.
    """
    px, py = centre(person)
    bx, by = centre(bicycle)
    pw, ph = max(1.0, person[2] - person[0]), max(1.0, person[3] - person[1])
    bw, bh = max(1.0, bicycle[2] - bicycle[0]), max(1.0, bicycle[3] - bicycle[1])
    overlap = intersection_area(person, bicycle) / max(1.0, min(area(person), area(bicycle)))
    horizontally_aligned = abs(px - bx) <= 0.75 * max(pw, bw)
    bike_under_or_through_person = bicycle[1] <= person[3] + 0.20 * ph and by >= py - 0.15 * ph
    return overlap >= 0.025 or (horizontally_aligned and bike_under_or_through_person and abs(py - by) <= 0.9 * max(ph, bh))


def vehicle_containment(person, vehicle):
    """Vehicle occupant evidence: most of a person box lies inside a vehicle box."""
    return intersection_area(person, vehicle) / max(1.0, area(person)) >= 0.55


def observations_summary(track_id, observations, fps, diagonal):
    observations.sort(key=lambda x: x["frame"])
    total = len(observations)
    walk = sum(o["on_foot"] for o in observations)
    ride = sum(o["rider"] for o in observations)
    vehicle = sum(o["vehicle"] for o in observations)
    # A consistently riding track is excluded. A brief unassociated detection
    # is not enough to convert a mostly detected rider into a pedestrian.
    if walk == 0:
        status = "excluded_rider_or_vehicle"
    elif ride > 0 and ride * 2 >= total and walk < 2:
        status = "excluded_probable_rider"
    else:
        status = "candidate"
    first, last = observations[0], observations[-1]
    recent = observations[-min(5, total):]
    if len(recent) >= 2 and recent[-1]["frame"] > recent[0]["frame"]:
        c0, c1 = centre(recent[0]["box"]), centre(recent[-1]["box"])
        df = recent[-1]["frame"] - recent[0]["frame"]
        velocity = ((c1[0] - c0[0]) / df, (c1[1] - c0[1]) / df)
    else:
        velocity = (0.0, 0.0)
    heights = [max(1.0, o["box"][3] - o["box"][1]) for o in observations]
    return {
        "id": int(track_id), "status": status, "frames": total,
        "on_foot_frames": walk, "rider_frames": ride, "vehicle_frames": vehicle,
        "first_frame": first["frame"], "last_frame": last["frame"],
        "first_box": first["box"], "last_box": last["box"],
        "first_center": centre(first["box"]), "last_center": centre(last["box"]),
        "velocity_per_frame": velocity, "scale": sorted(heights)[len(heights) // 2],
        "fps": fps, "diagonal": diagonal,
    }


def can_join(a, b):
    """Conservative post-tracker association based on time and image geometry."""
    if a["status"] != "candidate" or b["status"] != "candidate":
        return False
    if a["last_frame"] >= b["first_frame"]:
        return False
    gap_frames = b["first_frame"] - a["last_frame"]
    gap_seconds = gap_frames / max(a["fps"], 1.0)
    # Only repair short interruptions; long re-entries need human review.
    if gap_seconds > 2.0:
        return False
    ax, ay = a["last_center"]
    vx, vy = a["velocity_per_frame"]
    predicted = (ax + vx * gap_frames, ay + vy * gap_frames)
    bx, by = b["first_center"]
    distance = math.hypot(predicted[0] - bx, predicted[1] - by)
    # Gate scales with subject size, image geometry, and observed elapsed time,
    # rather than using a resolution-specific fixed-pixel threshold.
    gate = max(1.5 * max(a["scale"], b["scale"]), 0.03 * a["diagonal"]) + 0.04 * a["diagonal"] * gap_seconds
    return distance <= gate


class UnionFind:
    def __init__(self, values):
        self.parent = {v: v for v in values}
    def find(self, value):
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value
    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a


def analyse_video(path, model_name, confidence, imgsz):
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as exc:
        fail("missing required dependency; install ultralytics, opencv-python, and openpyxl: " + str(exc))
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        fail(f"cannot open video: {path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    if width <= 0 or height <= 0:
        fail(f"video has invalid dimensions: {path}")
    diagonal = math.hypot(width, height)
    # Fresh model per source prevents state leakage between independently named videos.
    model = YOLO(model_name)
    tracks = defaultdict(list)
    # COCO: person=0, bicycle=1, car=2, motorcycle=3, bus=5, truck=7.
    relevant_classes = [0, 1, 2, 3, 5, 7]
    stream = model.track(
        source=str(path), stream=True, persist=True, tracker="bytetrack.yaml",
        classes=relevant_classes, conf=confidence, iou=0.5, imgsz=imgsz, verbose=False,
    )
    for frame_index, result in enumerate(stream):
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue
        xyxy = boxes.xyxy.cpu().tolist()
        classes = [int(x) for x in boxes.cls.cpu().tolist()]
        ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(classes)
        bicycles = [b for b, c in zip(xyxy, classes) if c == 1]
        vehicles = [b for b, c in zip(xyxy, classes) if c in {2, 3, 5, 7}]
        for box, cls, track_id in zip(xyxy, classes, ids):
            if cls != 0 or track_id is None:
                continue
            rider = any(bicycle_relation(box, b) for b in bicycles)
            occupant = any(vehicle_containment(box, v) for v in vehicles)
            tracks[int(track_id)].append({
                "frame": frame_index, "box": [round(float(x), 3) for x in box],
                "rider": rider, "vehicle": occupant, "on_foot": not rider and not occupant,
            })
    summaries = [observations_summary(track_id, obs, fps, diagonal) for track_id, obs in tracks.items()]
    summaries.sort(key=lambda x: (x["first_frame"], x["id"]))
    candidates = [s for s in summaries if s["status"] == "candidate"]
    uf = UnionFind([s["id"] for s in candidates])
    joins = []
    # For every chronological pair, repair only a short, compatible broken track.
    for index, left in enumerate(candidates):
        for right in candidates[index + 1:]:
            if right["first_frame"] <= left["last_frame"]:
                continue
            if (right["first_frame"] - left["last_frame"]) / fps > 2.0:
                break
            if can_join(left, right):
                uf.union(left["id"], right["id"])
                joins.append([left["id"], right["id"]])
    groups = defaultdict(list)
    for item in candidates:
        groups[uf.find(item["id"])].append(item["id"])
    diagnostic = {
        "video": path.name, "fps": fps, "width": width, "height": height,
        "raw_tracklets": summaries, "repaired_track_groups": sorted(groups.values()),
        "joins": joins, "computed_count": len(groups),
    }
    return len(groups), diagnostic


def write_workbook(rows, output_path):
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        fail("missing required dependency openpyxl: " + str(exc))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "results"
    worksheet.append(["filename", "number"])
    for filename, number in rows:
        worksheet.append([filename, int(number)])
    # Atomic replacement avoids leaving a partially written workbook if saving fails.
    fd, temporary_name = tempfile.mkstemp(prefix=".count-", suffix=".xlsx", dir=str(output_path.parent))
    os.close(fd)
    try:
        workbook.save(temporary_name)
        os.replace(temporary_name, output_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main():
    request = load_request()
    if "video_dir" not in request or "output_path" not in request:
        fail("video_dir and output_path are required")
    video_dir = Path(request["video_dir"]).expanduser().resolve()
    output_path = Path(request["output_path"]).expanduser().resolve()
    if not video_dir.is_dir():
        fail(f"video_dir is not a directory: {video_dir}")
    model_name = request.get("model", "yolov8s.pt")
    confidence = float(request.get("confidence", 0.20))
    imgsz = int(request.get("imgsz", 640))
    if not isinstance(model_name, str) or not model_name:
        fail("model must be a nonempty weight name or path")
    if not 0.0 < confidence < 1.0 or imgsz < 160:
        fail("confidence must be in (0,1) and imgsz must be at least 160")
    overrides = request.get("review_overrides", {})
    if not isinstance(overrides, dict):
        fail("review_overrides must be an object of filename to integer")
    files = video_files(video_dir)
    known_names = {p.name for p in files}
    if set(overrides) - known_names:
        fail("review_overrides contains a filename not found in video_dir")
    for name, value in overrides.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            fail(f"override for {name} must be a nonnegative integer")
    all_diagnostics, rows, report_videos = [], [], []
    for path in files:
        calculated, diagnostic = analyse_video(path, model_name, confidence, imgsz)
        final_number = overrides.get(path.name, calculated)
        diagnostic["final_count"] = final_number
        diagnostic["override_used"] = path.name in overrides
        all_diagnostics.append(diagnostic)
        rows.append((path.name, final_number))
        report_videos.append({"filename": path.name, "number": final_number, "override_used": path.name in overrides})
    write_workbook(rows, output_path)
    diagnostic_path = request.get("diagnostics_path")
    if diagnostic_path is not None:
        diagnostic_path = Path(diagnostic_path).expanduser().resolve()
        diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostic_path.write_text(json.dumps({"videos": all_diagnostics}, indent=2), encoding="utf-8")
    print(json.dumps({"output_path": str(output_path), "diagnostics_path": str(diagnostic_path) if diagnostic_path else None, "videos": report_videos}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(2)
