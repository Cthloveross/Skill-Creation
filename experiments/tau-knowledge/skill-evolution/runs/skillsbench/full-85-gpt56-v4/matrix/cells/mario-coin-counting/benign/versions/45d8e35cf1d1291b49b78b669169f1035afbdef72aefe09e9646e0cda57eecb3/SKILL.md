---
name: mario-keyframe-template-counting
description: Extract codec keyframes from a video, overwrite them as grayscale PNGs, and count occurrences of supplied sprite templates with grayscale template matching and non-maximum suppression. Use for per-keyframe game-object counting tasks that require a strict CSV ledger.
---

# Mario keyframe template counting

This Skill extracts only encoded I/key frames in presentation order, converts the resulting frame PNGs to single-channel grayscale **in place**, detects supplied templates in every frame, and writes a four-column CSV. It uses the same grayscale conversion for frames and templates, then counts local maxima after non-maximum suppression rather than score-map pixels.

## Prerequisites

* `ffmpeg` and `ffprobe` must be on `PATH`.
* Python must provide `cv2` (OpenCV) and `numpy`.
* The video and each template must exist and be readable images.

## Run

Run the entry point from any directory. It reads one JSON object from stdin and emits a JSON report to stdout:

```sh
python3 /app/environment/skills/current/scripts/count_keyframes.py <<'JSON'
{
  "video": "/root/super-mario.mp4",
  "templates": {
    "coins": "/root/coin.png",
    "enemies": "/root/enemy.png",
    "turtles": "/root/turtle.png"
  },
  "frame_pattern": "/root/keyframes_%03d.png",
  "csv": "/root/counting_results.csv"
}
JSON
```

Input fields are:

* `video` (string): source video.
* `templates` (object): output CSV count-column name to template image path. For the Mario task, use exactly `coins`, `enemies`, and `turtles`.
* `frame_pattern` (string): numbered PNG pattern accepted by ffmpeg, normally an absolute `.../keyframes_%03d.png` pattern.
* `csv` (string): result location.
* Optional `thresholds` (object): per-label normalized correlation minimums, default `0.75`.
* Optional `scales` (array of positive numbers): template scales to try, default `[1.0]`. Keep `[1.0]` where templates originate from the recording; use a small explicit set only if sprite scale truly changes.
* Optional `nms_overlap` (number in `(0,1]`): overlap allowed before duplicate candidate suppression, default `0.35`.

The standard invocation creates `/root/keyframes_001.png`, `/root/keyframes_002.png`, etc.; they are grayscale PNGs after the command returns. The CSV has exactly `frame_id,coins,enemies,turtles` when those template labels are supplied. Frame IDs are absolute paths generated from the actual written names and are in timeline order.

## Interpreting and validating the result

The JSON report contains per-template accepted score summaries and the recorded ffprobe metadata. Inspect low accepted scores and unusually dense detections; if necessary, rerun with a justified per-object `thresholds` adjustment. Do not count all correlation pixels above a cutoff: this script uses peak candidates plus NMS.

The program fails rather than writes a partial ledger if extraction produces no frames, a frame is not grayscale, CSV rows are not one-for-one with frames, required columns differ, a numeric count is invalid, or a frame cannot be reopened. It removes only old files matching the requested numbered pattern before extracting, so stale keyframe files cannot enter the CSV.

Codec keyframes are selected with ffmpeg's `pict_type=I` selection and `-vsync 0`; no frame-rate conversion is used. This preserves the selected decode/presentation order rather than sampling arbitrary video frames.
