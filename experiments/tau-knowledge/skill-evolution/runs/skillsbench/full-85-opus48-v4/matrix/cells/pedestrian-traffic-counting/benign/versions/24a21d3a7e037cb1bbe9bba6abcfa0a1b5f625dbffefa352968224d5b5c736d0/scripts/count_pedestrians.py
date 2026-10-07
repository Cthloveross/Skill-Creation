#!/usr/bin/env python3
"""Entrypoint: scan a video directory, count unique pedestrians per video, and
write a strict results.xlsx.

stdin JSON (see SKILL.md). stdout JSON report. Side effect: writes xlsx.
"""
from __future__ import annotations
import json
import os
import sys
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg")


def _ensure_deps():
    try:
        import ultralytics  # noqa: F401
        import cv2  # noqa: F401
        return True, None
    except Exception:
        pass
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "ultralytics", "opencv-python", "lap"],
            check=False,
        )
    except Exception as e:  # pragma: no cover
        return False, f"pip install failed: {e}"
    try:
        import ultralytics  # noqa: F401
        import cv2  # noqa: F401
        return True, None
    except Exception as e:
        return False, f"ultralytics/opencv unavailable: {e}"


def list_videos(video_dir, output_path):
    out_abs = os.path.abspath(output_path)
    files = []
    for name in os.listdir(video_dir):
        p = os.path.join(video_dir, name)
        if not os.path.isfile(p):
            continue
        if os.path.abspath(p) == out_abs:
            continue
        if name.lower().endswith(VIDEO_EXTS):
            files.append(name)
    return sorted(files)


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    video_dir = req.get("video_dir", "/app/video")
    output_path = req.get("output_path", os.path.join(video_dir, "count.xlsx"))
    model = req.get("model", "yolov8n.pt")
    conf = float(req.get("conf", 0.3))
    iou = float(req.get("iou", 0.5))
    strides = req.get("strides", None)
    min_frames = int(req.get("min_frames", 2))
    riding_frac = float(req.get("riding_frac", 0.4))

    errors = []
    results = []
    details = {}

    if not os.path.isdir(video_dir):
        print(json.dumps({"results": [], "output_path": output_path,
                          "errors": [f"video_dir not found: {video_dir}"]}))
        return 1

    videos = list_videos(video_dir, output_path)
    if not videos:
        print(json.dumps({"results": [], "output_path": output_path,
                          "errors": ["no video files found"]}))
        return 1

    ok, dep_err = _ensure_deps()
    if not ok:
        print(json.dumps({"results": [], "output_path": output_path,
                          "errors": [dep_err or "dependencies missing"]}))
        return 2

    import pedestrian_core as pc

    for name in videos:
        path = os.path.join(video_dir, name)
        try:
            info = pc.count_video(
                path, model=model, conf=conf, iou=iou,
                min_frames=min_frames, riding_frac=riding_frac,
                strides=strides,
            )
            results.append({"filename": name, "number": int(info["number"])})
            details[name] = {k: v for k, v in info.items() if k != "kept_ids"}
        except Exception as e:
            errors.append(f"{name}: {e}")

    if not results:
        print(json.dumps({"results": [], "output_path": output_path,
                          "details": details, "errors": errors}))
        return 3

    from write_results import write_results
    results_sorted = sorted(results, key=lambda r: r["filename"])
    write_results(output_path, results_sorted)

    print(json.dumps({
        "results": results_sorted,
        "output_path": output_path,
        "details": details,
        "errors": errors,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
