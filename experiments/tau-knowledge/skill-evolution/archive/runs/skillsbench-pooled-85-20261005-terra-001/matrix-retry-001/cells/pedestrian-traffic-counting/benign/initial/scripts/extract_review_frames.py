#!/usr/bin/env python3
"""Create a chronological video contact sheet. JSON stdin, JSON stdout."""
import json
import math
import sys
from pathlib import Path


def main():
    request = json.load(sys.stdin)
    video_path = Path(request["video_path"]).expanduser().resolve()
    output_path = Path(request["output_path"]).expanduser().resolve()
    interval = float(request.get("interval_seconds", 1.0))
    width = int(request.get("frame_width", 320))
    columns = int(request.get("columns", 4))
    if not video_path.is_file() or interval <= 0 or width < 80 or columns < 1:
        raise ValueError("invalid video_path, interval_seconds, frame_width, or columns")
    import cv2
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"cannot open {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
    step = max(1, round(interval * fps))
    frames, index = [], 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index % step == 0:
            h, w = frame.shape[:2]
            scaled_h = max(1, round(h * width / w))
            frame = cv2.resize(frame, (width, scaled_h))
            cv2.putText(frame, f"t={index / fps:.1f}s", (6, min(scaled_h - 7, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
            frames.append(frame)
        index += 1
    capture.release()
    if not frames:
        raise ValueError("video contained no readable frames")
    tile_h = max(f.shape[0] for f in frames)
    tiles = []
    for frame in frames:
        tiles.append(cv2.copyMakeBorder(frame, 0, tile_h - frame.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0)))
    blank = tiles[0] * 0
    while len(tiles) % columns:
        tiles.append(blank.copy())
    rows = [cv2.hconcat(tiles[i:i + columns]) for i in range(0, len(tiles), columns)]
    contact_sheet = cv2.vconcat(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), contact_sheet):
        raise ValueError(f"could not write {output_path}")
    print(json.dumps({"output_path": str(output_path), "sampled_frames": len(frames), "fps": fps, "interval_seconds": interval}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(2)
