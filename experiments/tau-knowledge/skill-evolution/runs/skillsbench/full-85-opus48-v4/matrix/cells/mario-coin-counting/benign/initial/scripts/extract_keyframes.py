#!/usr/bin/env python3
"""Extract codec key frames with ffmpeg, preserving presentation order.

stdin:  {"video": path, "out_dir": dir, "basename": "keyframes"}
stdout: {"frames": [sorted paths], "count": N}
"""
import glob
import json
import os
import subprocess
import sys


def main():
    cfg = json.load(sys.stdin)
    video = cfg["video"]
    out_dir = cfg.get("out_dir", os.path.dirname(video) or ".")
    basename = cfg.get("basename", "keyframes")
    if not os.path.isfile(video):
        raise FileNotFoundError("video not found: %s" % video)
    os.makedirs(out_dir, exist_ok=True)

    pattern = os.path.join(out_dir, basename + "_%03d.png")
    glob_pat = os.path.join(out_dir, basename + "_*.png")
    # Remove stale frames so the count reflects this run only.
    for old in glob.glob(glob_pat):
        try:
            os.remove(old)
        except OSError:
            pass

    # -skip_frame nokey keeps only self-contained (key) frames.
    # -vsync vfr (passthrough) avoids frame-rate duplication/dropping.
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-skip_frame", "nokey", "-i", video,
        "-an", "-vsync", "vfr", pattern,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    frames = sorted(glob.glob(glob_pat))
    if proc.returncode != 0 or not frames:
        # Fallback: explicit I-frame selection filter.
        for old in frames:
            try:
                os.remove(old)
            except OSError:
                pass
        cmd2 = [
            "ffmpeg", "-y", "-loglevel", "error", "-i", video,
            "-an", "-vf", "select=eq(pict_type\\,I)",
            "-vsync", "vfr", pattern,
        ]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True)
        frames = sorted(glob.glob(glob_pat))
        if proc2.returncode != 0 or not frames:
            raise RuntimeError(
                "ffmpeg key-frame extraction failed. primary stderr: %s ; "
                "fallback stderr: %s" % (proc.stderr, proc2.stderr))

    json.dump({"frames": frames, "count": len(frames)}, sys.stdout)


if __name__ == "__main__":
    main()
