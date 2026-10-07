---
name: pedestrian-video-count-to-xlsx
description: Count unique on-foot pedestrians across one or more fixed-camera videos with detector-assisted multi-object tracking, exclude riders and vehicle occupants, and create the strict single-sheet count.xlsx workbook required by pedestrian-counting tasks.
---

# Pedestrian video counting

Use this Skill when a directory of surveillance videos must be converted to a two-column Excel workbook of **unique physical pedestrians**. It is designed for fixed public-street cameras. It does not sum frame-level detections: each tracker identity is recorded as a tracklet and a conservative temporal/spatial reconciliation pass joins likely fragments.

## Prerequisites

The execution runtime needs Python 3 plus `ultralytics`, `opencv-python` (or `opencv-python-headless`), and `openpyxl`. The detector weights are downloaded by Ultralytics on first use, so network access or a pre-cached model is required. For example, the execution agent may install missing dependencies before running the script:

```bash
python -m pip install ultralytics opencv-python-headless openpyxl
```

A CPU-only runtime is supported. The default `yolov8m.pt` is a practical accuracy/speed choice; use `yolov8l.pt` or `yolov8x.pt` where video length and runtime permit. Do not replace tracking with a sum of per-frame person boxes.

## Run

The main script reads JSON from stdin and writes a JSON status object to stdout. It writes the requested workbook itself.

```bash
python scripts/build_count.py <<'JSON'
{"input_dir":"/app/video","output_path":"/app/video/count.xlsx","model":"yolov8m.pt","audit_path":"/app/video/pedestrian_track_audit.json"}
JSON
```

Input fields:

- `input_dir` (optional, default `/app/video`): directory recursively searched for common video extensions.
- `output_path` (optional, default `<input_dir>/count.xlsx`): `.xlsx` destination.
- `model` (optional, default `yolov8m.pt`): an Ultralytics detection model or a local weights path.
- `confidence` (optional, default `0.20`): detector confidence in `(0, 1)`.
- `max_sampled_frames` (optional, default `1400`): upper target for sampled frames per video. The script derives its stride from measured frame count, rather than assuming a particular FPS.
- `audit_path` (optional): where to write a JSON tracklet ledger. Keep it outside the workbook; it is not needed by downstream workbook consumers.

The script considers a pedestrian to be a visible person traveling on foot. Person tracks consistently associated with a bicycle, motorcycle, or enclosing road vehicle are excluded. A nearby but non-overlapping vehicle alone does not cause exclusion. The association is deliberately conservative because a person walking beside a bicycle is still a pedestrian.

## Review and robustness

Read the status JSON and, when supplied, the audit ledger. Review tracklets with short duration, category disagreement, and any conservative fragment joins against the source video. Also rerun with a nearby defensible sampling budget (for example, `1000` and `1600`) or a nearby confidence threshold. Large count changes indicate missed appearances, tracker fragmentation, or overly aggressive matching; resolve those by inspecting the affected tracklets rather than selecting a count from a desired result.

The tracker has no reliable person re-identification embedding in this portable implementation. Therefore its second pass only merges non-overlapping identities if the old endpoint predicts the new start within a scale- and time-derived gate. It intentionally avoids appearance-only matching of similarly dressed simultaneous pedestrians.

## Validate the artifact

After generation, validate the final workbook structurally:

```bash
python scripts/validate_workbook.py <<'JSON'
{"path":"/app/video/count.xlsx","input_dir":"/app/video"}
JSON
```

Validation checks that there is exactly one `results` sheet; its entire populated content is exactly the `filename`, `number` header and one sorted row per source video; and every count is a nonnegative integer. The workbook contains no audit data, blank rows, extra columns, summary rows, or additional sheets.

If a video cannot be decoded, a model cannot be loaded, or no source videos are found, `build_count.py` returns a JSON error and does not claim successful output. Resolve the prerequisite or source issue before delivering the workbook.
