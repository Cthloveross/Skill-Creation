---
name: mario-keyframe-template-counting
description: Extract codec key frames from a video, overwrite the extracted PNGs as grayscale, and count occurrences of supplied sprite templates per frame with calibrated template matching and non-maximum suppression. Use for Super Mario-style video object-counting tasks that require a strict frame-path CSV.
---

# Mario key-frame template counting

This skill produces key-frame images and one CSV record for each image. It is intended for tasks that supply a video plus reference images for coins, enemies, and turtles, but the script accepts any mapping of output count column to template path.

## Method

1. Verify that the video and all template paths exist and that OpenCV (`cv2`) and NumPy are importable.
2. Use `ffprobe` to determine the number of decodable codec key frames, then use `ffmpeg -skip_frame nokey` with passthrough sync to extract only those frames in presentation order. Existing files for the selected keyframe prefix are removed first so stale frames cannot enter the CSV.
3. Reopen each written PNG, convert it to a single grayscale channel, and write it back to exactly the same path. Templates are passed through the same grayscale conversion pipeline in memory.
4. For each template/frame pair, compute a normalized template-response map. Thresholds are calibrated from that particular response map using both Otsu separation and its high background-response quantile; no fixed correlation cutoff is used. Candidate locations are local response peaks, then non-maximum suppression uses a radius derived from the current template dimensions. Thus clusters of response pixels do not become multiple objects.
5. Write the required CSV in numeric frame order and reopen it and every PNG to validate: exact columns, exactly one row for every written frame, canonical absolute frame IDs, integer nonnegative counts, grayscale encoding, and key-frame metadata/file-count agreement.

The method assumes that each reference image is a crop at the same rendered scale as the corresponding object in the video. It intentionally does not sum detections across frames: the requested output is a count per key frame, not a count of unique objects over the whole video.

## Runtime interface

Run the packaged script with JSON on standard input. It writes one JSON object to standard output. On error, it writes `{"ok": false, "error": ...}` to standard output and exits nonzero.

Required JSON fields:

- `video_path`: source MP4 path.
- `templates`: object whose keys are CSV count columns and whose values are template image paths.

Optional fields:

- `output_dir` (default `/root`): directory for extracted frames.
- `keyframe_prefix` (default `keyframes_`): extracted file names are `<prefix>%03d.png`.
- `csv_path` (default `/root/counting_results.csv`): output CSV path.
- `frame_id_dir` (default to `output_dir`): directory represented in CSV frame IDs. Use an absolute path for the required `/root/keyframes_%03d.png` format.

For the stated task, invoke it as follows (the executor runs this, rather than treating this example as a result):

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A successful response includes the number of extracted frames, CSV path, per-template calibration summaries, and validation status. The executor should only deliver the CSV after `validation.ok` is true. The generated CSV has precisely `frame_id,coins,enemies,turtles` for the invocation above, with `frame_id` values `/root/keyframes_001.png`, `/root/keyframes_002.png`, and so on in timeline order.

## Failure handling

Missing inputs, unwritable destinations, missing `ffmpeg`/`ffprobe`, missing OpenCV/NumPy, no decoded key frames, a template larger than a frame, extraction/metadata disagreement, or validation failures are explicit errors. Do not substitute sampled non-key frames or silently retain stale keyframe files. If calibration results are visibly implausible, inspect the emitted `calibration` values and supply template crops at the video render scale rather than applying a task-independent hard-coded threshold.
