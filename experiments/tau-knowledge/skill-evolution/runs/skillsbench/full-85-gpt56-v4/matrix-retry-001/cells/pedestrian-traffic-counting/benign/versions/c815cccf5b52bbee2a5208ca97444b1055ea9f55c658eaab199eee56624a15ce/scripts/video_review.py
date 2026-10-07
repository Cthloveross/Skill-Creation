#!/usr/bin/env python3
"""Extract timestamp-labeled video contact sheets for chronological pedestrian review."""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def label(frame, text):
    out = frame.copy()
    cv2.rectangle(out, (0, 0), (240, 31), (0, 0, 0), -1)
    cv2.putText(out, text, (7, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float)
    ap.add_argument("--columns", type=int, default=4)
    ap.add_argument("--width", type=int, default=400)
    args = ap.parse_args()
    if args.interval <= 0 or args.columns < 1 or args.width < 32 or args.start < 0:
        raise SystemExit("interval must be >0, columns/width valid, and start >=0")
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {args.video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 else 0.0
    end = duration if args.end is None else min(args.end, duration)
    if end < args.start:
        raise SystemExit("end precedes start")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    times = []
    t = args.start
    while t <= end + 1e-8:
        times.append(t)
        t += args.interval
    if times and end - times[-1] > 0.02:
        times.append(end)
    thumbs = []
    written = []
    for index, timestamp in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        h, w = frame.shape[:2]
        new_h = max(1, round(h * args.width / w))
        thumb = cv2.resize(frame, (args.width, new_h), interpolation=cv2.INTER_AREA)
        thumbs.append(label(thumb, f"t={timestamp:.2f}s"))
        if len(thumbs) == args.columns or index == len(times) - 1:
            tile_h = max(x.shape[0] for x in thumbs)
            padded = [cv2.copyMakeBorder(x, 0, tile_h-x.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(25,25,25)) for x in thumbs]
            while len(padded) < args.columns:
                padded.append(np.zeros((tile_h, args.width, 3), dtype=np.uint8))
            sheet = np.hstack(padded)
            name = f"sheet_{len(written):03d}.jpg"
            cv2.imwrite(str(out_dir / name), sheet)
            written.append(name)
            thumbs = []
    cap.release()
    print(json.dumps({"video": args.video, "fps": fps, "frame_count": frame_count, "duration_sec": duration, "requested_interval_sec": args.interval, "contact_sheets": written}))

if __name__ == "__main__":
    main()
