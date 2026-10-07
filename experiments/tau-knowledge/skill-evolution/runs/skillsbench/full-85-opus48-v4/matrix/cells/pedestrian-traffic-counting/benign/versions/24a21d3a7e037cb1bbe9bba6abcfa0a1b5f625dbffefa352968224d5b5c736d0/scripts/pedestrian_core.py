"""Core pedestrian counting via YOLO detection + ByteTrack tracking.

Public function: count_video(path, model, stride, conf, iou, min_frames,
riding_frac) -> dict with keys: number, kept_ids, cyclist_ids, total_person_ids.

Deduplication principle: each unique track ID is one physical person; a person
visible across many frames shares one ID and is counted once. Cyclists are
excluded when their person box overlaps a bicycle/motorcycle in a large fraction
of the frames in which they appear.

This module imports ultralytics lazily so callers can attempt an install first.
"""
from __future__ import annotations
import os
from collections import defaultdict

# COCO class ids
PERSON = 0
BICYCLE = 1
MOTORCYCLE = 3
VEHICLE_LIKE = {BICYCLE, MOTORCYCLE}


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    aarea = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
    barea = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
    union = aarea + barea - inter
    return inter / union if union > 0 else 0.0


def _overlap_over_min(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    aarea = max(1e-6, (ax2 - ax1) * (ay2 - ay1))
    barea = max(1e-6, (bx2 - bx1) * (by2 - by1))
    return inter / min(aarea, barea)


def get_fps(path):
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if fps and fps > 0:
            return float(fps)
    except Exception:
        pass
    return 30.0


def auto_stride(path, target_fps=10.0):
    fps = get_fps(path)
    s = int(round(fps / target_fps))
    return max(1, s)


def _load_model(model_name):
    from ultralytics import YOLO  # lazy import
    return YOLO(model_name)


def _track_once(model, path, stride, conf, iou):
    """Return per-track aggregated info for one stride run.

    tracks[id] = {"cls_counts": {cls:n}, "frames": n, "riding": n}
    """
    tracks = defaultdict(lambda: {"cls_counts": defaultdict(int), "frames": 0, "riding": 0})
    gen = model.track(
        source=path,
        persist=True,
        stream=True,
        vid_stride=stride,
        classes=[PERSON, BICYCLE, MOTORCYCLE],
        conf=conf,
        iou=iou,
        tracker="bytetrack.yaml",
        verbose=False,
    )
    for r in gen:
        boxes = getattr(r, "boxes", None)
        if boxes is None or boxes.id is None:
            continue
        ids = boxes.id.int().cpu().tolist()
        clss = boxes.cls.int().cpu().tolist()
        xyxy = boxes.xyxy.cpu().tolist()
        bikes = [xyxy[i] for i in range(len(clss)) if clss[i] in VEHICLE_LIKE]
        for i, tid in enumerate(ids):
            cls = clss[i]
            t = tracks[tid]
            t["cls_counts"][cls] += 1
            t["frames"] += 1
            if cls == PERSON and bikes:
                pb = xyxy[i]
                riding = any(
                    _iou(pb, bb) > 0.2 or _overlap_over_min(pb, bb) > 0.5
                    for bb in bikes
                )
                if riding:
                    t["riding"] += 1
    return tracks


def _count_from_tracks(tracks, min_frames, riding_frac):
    kept, cyclists, total_person = [], [], []
    for tid, t in tracks.items():
        person_frames = t["cls_counts"].get(PERSON, 0)
        if person_frames <= 0:
            continue
        # dominant class must be person
        if person_frames < max(t["cls_counts"].values()):
            continue
        total_person.append(tid)
        if t["frames"] < min_frames:
            continue
        frac_riding = t["riding"] / float(t["frames"]) if t["frames"] else 0.0
        if frac_riding >= riding_frac:
            cyclists.append(tid)
            continue
        kept.append(tid)
    return kept, cyclists, total_person


def count_video(path, model="yolov8n.pt", stride=None, conf=0.3, iou=0.5,
                min_frames=2, riding_frac=0.4, strides=None):
    """Count unique pedestrians in one video.

    Runs the pipeline at a primary stride (finest) and reports counts at the
    other strides for a perturbation-stability check. The returned ``number``
    uses the finest stride (most temporal coverage -> least fragmentation).
    """
    m = _load_model(model)
    if strides is None:
        base = stride if stride else auto_stride(path)
        strides = sorted({max(1, base), max(1, base + 1), max(1, base * 2)})
    strides = sorted({max(1, int(s)) for s in strides})
    stability = {}
    primary = strides[0]
    primary_kept = None
    for s in strides:
        tracks = _track_once(m, path, s, conf, iou)
        kept, cyclists, total_person = _count_from_tracks(tracks, min_frames, riding_frac)
        stability[s] = {
            "pedestrians": len(kept),
            "cyclists": len(cyclists),
            "total_person_ids": len(total_person),
        }
        if s == primary:
            primary_kept = (kept, cyclists, total_person)
    kept, cyclists, total_person = primary_kept
    return {
        "number": len(kept),
        "primary_stride": primary,
        "kept_ids": kept,
        "cyclist_ids": cyclists,
        "total_person_ids": len(total_person),
        "stability": stability,
    }
