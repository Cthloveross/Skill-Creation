---
name: pedestrian-video-counting
version: 1.0.0
description: Count unique on-foot pedestrians in one or more fixed-camera videos with YOLO detection, temporal tracking, conservative tracklet stitching, and an exactly structured XLSX result workbook. Use for surveillance-video tasks that require one count per source video rather than per-frame person totals.
---

# Pedestrian video counting

Use this skill when the required result is a count of **unique people travelling on foot** in each video. It deliberately does not sum frame detections. Cyclists, motorcyclists, and people whose visible position indicates that they are occupants of a vehicle are excluded.

## Prerequisites

The runtime needs Python 3 plus `ultralytics`, `opencv-python`, `numpy`, and `openpyxl`. The default model name, `yolo11x.pt`, is downloaded by Ultralytics on first use when it is not already cached. For a CPU-only or constrained runtime, choose `yolo11l.pt` or `yolo11m.pt` in the JSON input; do not reduce the review/validation steps just because a smaller detector is used.

The script reads its complete configuration as one JSON object from standard input and writes a JSON run report to standard output. It creates the requested workbook itself.

## Run

For the supplied task, run from the Skill directory (or use an absolute script path):

```sh
python scripts/count_pedestrians.py <<'JSON'
{"source_dir":"/app/video","output_path":"/app/video/count.xlsx"}
JSON
```

Input fields:

- `source_dir` (required): directory recursively searched for video files.
- `output_path` (required): destination `.xlsx` file.
- `weights` (optional, default `yolo11x.pt`): Ultralytics detection model.
- `confidence` (optional, default `0.22`): detector confidence in `(0,1)`.
- `stride` (optional, default `1`): analyze every Nth decoded frame. Keep `1` unless the source is unusually long; increasing it can miss brief appearances and weaken identity association.
- `tracker` (optional, default `bytetrack.yaml`): an Ultralytics tracker configuration available to the runtime.
- `review_json` (optional): path for a tracklet ledger containing times, endpoints, vehicle-association evidence, and the final component mapping.

The result report includes discovered files, frame rates, raw tracking IDs, rejected rider/occupant IDs, stitched pedestrian components, and validation status. A model/download/decode failure is reported as an error and the script exits nonzero; it never silently substitutes a zero count.

## Method and review

1. Process the full video temporally with the detector and tracker. Each tracker ID becomes a ledger tracklet rather than an immediate count.
2. For every person detection, inspect same-frame bicycle, motorcycle, car, bus, and truck detections. Accumulate evidence that the person is spatially positioned on/in a vehicle. Only a sustained association rejects a tracklet, avoiding exclusion merely because somebody walks near a parked vehicle.
3. Stitch only non-overlapping pedestrian tracklets with a short elapsed-time gap and compatible predicted endpoint geometry. This conservative second pass addresses short tracker-ID losses without merging simultaneous people.
4. Inspect the optional review ledger, particularly one-frame tracks, rejected tracks, and joins near the stitch gate. If scene conditions make a different detector confidence or sampling rate defensible, rerun with nearby settings and compare the component count. Large instability calls for visual inspection of the corresponding video intervals, not averaging counts.
5. The script writes one row per discovered video sorted by relative filename. Counts are numeric integers.

The script validates the workbook after saving: exactly one sheet named `results`, exactly the `filename` and `number` headers, exactly one row per input video, sorted filenames, integer nonnegative counts, and no values outside the required rectangular table. A successful `workbook_valid: true` report is required before delivery.

The geometric vehicle test and conservative stitch pass are evidence-based heuristics, not a substitute for review in dense scenes. A person walking a bicycle remains eligible when vehicle-association evidence is not sustained.
