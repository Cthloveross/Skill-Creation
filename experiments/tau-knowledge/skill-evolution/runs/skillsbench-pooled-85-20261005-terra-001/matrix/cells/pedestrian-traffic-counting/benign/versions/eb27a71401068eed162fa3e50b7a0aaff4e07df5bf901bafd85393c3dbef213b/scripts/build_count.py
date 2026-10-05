#!/usr/bin/env python3
"""Create a strict pedestrian-count workbook from a directory of videos.

JSON stdin schema is documented in SKILL.md. JSON stdout is a success/error status.
Third-party progress is redirected to stderr so stdout remains machine-readable.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm", ".mpeg", ".mpg"}
PERSON = 0
BICYCLE_OR_MOTORCYCLE = {1, 3}
ROAD_VEHICLES = {2, 5, 6, 7}


@dataclass
class Observation:
    frame: int
    center_x: float
    center_y: float
    width: float
    height: float
    confidence: float
    on_foot: bool


@dataclass
class Tracklet:
    track_id: int
    observations: list[Observation] = field(default_factory=list)

    def add(self, obs: Observation) -> None:
        self.observations.append(obs)

    @property
    def first(self) -> Observation:
        return self.observations[0]

    @property
    def last(self) -> Observation:
        return self.observations[-1]

    @property
    def foot_fraction(self) -> float:
        return sum(x.on_foot for x in self.observations) / len(self.observations)

    def velocity(self) -> tuple[float, float]:
        """Robust endpoint velocity in pixels per sampled source frame."""
        if len(self.observations) < 2:
            return (0.0, 0.0)
        a = self.observations[max(0, len(self.observations) - 4)]
        b = self.last
        dt = max(1, b.frame - a.frame)
        return ((b.center_x - a.center_x) / dt, (b.center_y - a.center_y) / dt)


class UnionFind:
    def __init__(self, values: Iterable[int]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, a: int, b: int) -> None:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a


def box_values(box: Any) -> tuple[float, float, float, float]:
    values = box.xyxy[0].detach().cpu().tolist()
    return tuple(float(v) for v in values)  # type: ignore[return-value]


def center_size(rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = rect
    return ((x1 + x2) / 2, (y1 + y2) / 2, max(1.0, x2 - x1), max(1.0, y2 - y1))


def overlap_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def associated_with_transport(person: tuple[float, float, float, float], other: tuple[float, float, float, float], cls: int) -> bool:
    """Identify a rider/occupant without excluding a merely nearby pedestrian."""
    px, py, pw, ph = center_size(person)
    ox, oy, ow, oh = center_size(other)
    inter = overlap_area(person, other)
    person_area = pw * ph
    if cls in ROAD_VEHICLES:
        # An occupant is normally materially inside/overlapping the vehicle box.
        return inter / person_area > 0.45 or (other[0] <= px <= other[2] and other[1] <= py <= other[3])
    # A rider sits above the bicycle/motorcycle. Require horizontal alignment and
    # bicycle proximity/overlap; this avoids rejecting someone walking beside one.
    horizontal = abs(px - ox) <= 0.42 * (pw + ow)
    lower_relation = py - 0.15 * ph <= oy <= person[3] + 0.45 * ph
    return horizontal and lower_relation and (inter > 0 or oy >= py + 0.05 * ph)


def is_foot_detection(person_box: tuple[float, float, float, float], all_boxes: list[tuple[int, tuple[float, float, float, float]]]) -> bool:
    for cls, other in all_boxes:
        if cls in BICYCLE_OR_MOTORCYCLE or cls in ROAD_VEHICLES:
            if associated_with_transport(person_box, other, cls):
                return False
    return True


def reconcile(tracklets: dict[int, Tracklet], fps: float) -> tuple[list[list[int]], list[tuple[int, int]]]:
    """Conservatively join plausible tracker fragments using time and motion only."""
    ids = sorted(tracklets)
    uf = UnionFind(ids)
    joins: list[tuple[int, int]] = []
    # Use seconds, then express it in observed source-frame geometry.
    max_gap = max(1, int(round(2.5 * max(1.0, fps))))
    candidates: list[tuple[float, int, int]] = []
    for old_id in ids:
        old = tracklets[old_id]
        for new_id in ids:
            if old_id == new_id:
                continue
            new = tracklets[new_id]
            gap = new.first.frame - old.last.frame
            if gap <= 0 or gap > max_gap:
                continue
            vx, vy = old.velocity()
            predicted_x = old.last.center_x + vx * gap
            predicted_y = old.last.center_y + vy * gap
            distance = math.hypot(new.first.center_x - predicted_x, new.first.center_y - predicted_y)
            scale = max(old.last.width, old.last.height, new.first.width, new.first.height)
            speed_allowance = math.hypot(vx, vy) * gap * 0.65
            # Scale-normalized gate plus a motion-uncertainty component.
            gate = 1.25 * scale + speed_allowance
            if distance <= gate:
                candidates.append((distance / max(gate, 1.0), old_id, new_id))
    # One short disappearance should not permit a chain of broad merges. Greedy,
    # lowest-normalized-distance matching is more conservative than global merging.
    used_end: set[int] = set()
    used_start: set[int] = set()
    for _, old_id, new_id in sorted(candidates):
        if old_id in used_end or new_id in used_start:
            continue
        if uf.find(old_id) == uf.find(new_id):
            continue
        uf.union(old_id, new_id)
        used_end.add(old_id)
        used_start.add(new_id)
        joins.append((old_id, new_id))
    groups: dict[int, list[int]] = defaultdict(list)
    for track_id in ids:
        groups[uf.find(track_id)].append(track_id)
    return list(groups.values()), joins


def tracker_yaml(track_buffer: int) -> str:
    return "\n".join([
        "tracker_type: bytetrack",
        "track_high_thresh: 0.25",
        "track_low_thresh: 0.10",
        "new_track_thresh: 0.25",
        f"track_buffer: {track_buffer}",
        "match_thresh: 0.80",
        "fuse_score: True",
    ]) + "\n"


def count_video(video_path: Path, model: Any, confidence: float, max_sampled_frames: int) -> tuple[int, dict[str, Any]]:
    import cv2  # imported here to give a clear prerequisite error

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot decode video: {video_path}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    cap.release()
    if fps <= 0:
        fps = 30.0
    stride = max(1, math.ceil(frame_count / max(1, max_sampled_frames))) if frame_count else 1
    # The tracker sees sampled frames, so its lost-track buffer must be scaled.
    buffer = max(20, int(math.ceil((2.5 * fps) / stride)))
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as tmp:
        tmp.write(tracker_yaml(buffer))
        tracker_path = tmp.name
    tracklets: dict[int, Tracklet] = {}
    try:
        results = model.track(source=str(video_path), stream=True, persist=False,
                              tracker=tracker_path, conf=confidence, iou=0.55,
                              vid_stride=stride, verbose=False)
        for processed_index, result in enumerate(results):
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            all_boxes: list[tuple[int, tuple[float, float, float, float]]] = []
            for box in boxes:
                all_boxes.append((int(box.cls[0].item()), box_values(box)))
            source_frame = processed_index * stride
            for box in boxes:
                if int(box.cls[0].item()) != PERSON or box.id is None:
                    continue
                rect = box_values(box)
                cx, cy, width, height = center_size(rect)
                track_id = int(box.id[0].item())
                tracklets.setdefault(track_id, Tracklet(track_id)).add(Observation(
                    frame=source_frame, center_x=cx, center_y=cy, width=width, height=height,
                    confidence=float(box.conf[0].item()), on_foot=is_foot_detection(rect, all_boxes)))
    finally:
        try:
            os.unlink(tracker_path)
        except OSError:
            pass

    groups, joins = reconcile(tracklets, fps)
    accepted_groups: list[list[int]] = []
    group_details: list[dict[str, Any]] = []
    for group in groups:
        observations = [obs for track_id in group for obs in tracklets[track_id].observations]
        observations.sort(key=lambda obs: obs.frame)
        foot_fraction = sum(obs.on_foot for obs in observations) / len(observations)
        # Retain a track with mixed evidence unless transport association dominates.
        accepted = foot_fraction >= 0.50
        group_details.append({
            "track_ids": sorted(group), "accepted_as_pedestrian": accepted,
            "observations": len(observations), "first_frame": observations[0].frame,
            "last_frame": observations[-1].frame, "on_foot_fraction": round(foot_fraction, 4),
            "mean_confidence": round(sum(o.confidence for o in observations) / len(observations), 4),
        })
        if accepted:
            accepted_groups.append(group)
    audit = {
        "video": video_path.name, "fps": fps, "reported_frame_count": frame_count,
        "sampling_stride": stride, "raw_person_tracklets": len(tracklets),
        "fragment_joins": [{"from": a, "to": b} for a, b in joins],
        "groups": sorted(group_details, key=lambda x: (x["first_frame"], x["track_ids"])),
    }
    return len(accepted_groups), audit


def source_videos(input_dir: Path, output_path: Path) -> list[Path]:
    videos = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES]
    # Exclude any path that might accidentally be named like the workbook only by
    # extension filtering above; sort by source filename relative to supplied root.
    return sorted(videos, key=lambda p: p.relative_to(input_dir).as_posix().lower())


def write_workbook(rows: list[tuple[str, int]], output_path: Path) -> None:
    from openpyxl import Workbook
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(["filename", "number"])
    for filename, number in rows:
        ws.append([filename, int(number)])
    wb.save(output_path)


def main(payload: dict[str, Any]) -> dict[str, Any]:
    input_dir = Path(payload.get("input_dir", "/app/video")).resolve()
    output_path = Path(payload.get("output_path", input_dir / "count.xlsx")).resolve()
    model_name = str(payload.get("model", "yolov8m.pt"))
    confidence = float(payload.get("confidence", 0.20))
    max_sampled_frames = int(payload.get("max_sampled_frames", 1400))
    if not input_dir.is_dir():
        raise ValueError(f"input_dir is not a directory: {input_dir}")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be strictly between 0 and 1")
    if max_sampled_frames < 1:
        raise ValueError("max_sampled_frames must be positive")
    videos = source_videos(input_dir, output_path)
    if not videos:
        raise RuntimeError(f"no supported video files under {input_dir}")
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("missing ultralytics; install prerequisites from SKILL.md") from exc
    model = YOLO(model_name)
    rows: list[tuple[str, int]] = []
    audits: list[dict[str, Any]] = []
    for video in videos:
        count, audit = count_video(video, model, confidence, max_sampled_frames)
        # The requested schema calls for source filename. For ordinary flat input this
        # is basename; relative paths preserve uniqueness for recursively supplied input.
        filename = video.name if sum(p.name == video.name for p in videos) == 1 else video.relative_to(input_dir).as_posix()
        rows.append((filename, count))
        audits.append(audit)
    rows.sort(key=lambda row: row[0].lower())
    write_workbook(rows, output_path)
    audit_path = payload.get("audit_path")
    if audit_path:
        audit_destination = Path(str(audit_path))
        audit_destination.parent.mkdir(parents=True, exist_ok=True)
        audit_destination.write_text(json.dumps({"videos": audits}, indent=2), encoding="utf-8")
    return {"ok": True, "output_path": str(output_path), "videos": len(rows), "rows": [{"filename": f, "number": n} for f, n in rows]}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("stdin must contain a JSON object")
        # Libraries sometimes print model-download progress. Keep protocol stdout clean.
        with contextlib.redirect_stdout(sys.stderr):
            response = main(payload)
        print(json.dumps(response, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)
