# Method notes: pedestrian counting

## Goal
Count each physical pedestrian once per video, regardless of how many frames
they appear in, excluding cyclists/motorcyclists and vehicle occupants. Emit a
strict xlsx (`results` sheet, `filename`/`number`).

## Chosen pipeline (default): detection + tracking
- Detector: Ultralytics YOLO (`yolov8n.pt`, CPU-friendly, auto-downloads).
- Tracker: ByteTrack via `model.track(..., tracker='bytetrack.yaml', persist=True)`.
- Count = number of unique track IDs whose dominant class is `person`, after:
  - dropping tracks seen in fewer than `min_frames` sampled frames (noise),
  - dropping tracks whose person box overlaps a bicycle/motorcycle in at least
    `riding_frac` of their frames (cyclists).
- `vid_stride` sub-samples frames to keep CPU cost bounded; it is derived from
  the measured fps to target ~10 effective fps so brief appearances are still
  captured while retaining tracking continuity.

## Why these choices
- Per-frame counting overcounts massively; tracking deduplicates temporally.
- Person detectors fire on cyclists and vehicle occupants too, so semantic
  exclusion (bbox overlap with bikes) is required. Vehicle occupants are rarely
  detected and are not specially excluded to avoid wrongly dropping pedestrians
  walking in front of parked cars.

## Stability instead of tuning to a target
The pipeline runs at the finest stride plus one or two coarser strides and
reports unique-ID counts for each. Large swings between strides signal missed
brief appearances (too coarse), ID fragmentation (occlusions / lost IDs), or
over-merging. The reported number uses the finest stride (max temporal coverage,
least fragmentation). Do NOT tune parameters to reach any assumed count; adjust
only to reduce instability, then re-inspect.

## Reducing fragmentation / over-merging
- ByteTrack already bridges short gaps. If a single person is split into several
  IDs (count too high), consider: finer stride, higher tracker buffer
  (`track_buffer` in bytetrack.yaml), or a tracklet re-association pass that
  joins tracklets using elapsed time, motion extrapolation toward entry/exit
  regions, spatial compatibility and consistent walking-vs-riding evidence.
- Do not merge two co-existing similar-looking people on appearance alone.
- Normalize any pixel-distance gates by frame diagonal / box scale and express
  gap windows in seconds converted via the measured fps, so settings transfer
  across resolution and frame-rate.

## Alternative: holistic multimodal LLM
If a video-capable multimodal model with an API key is available, upload each
video, poll until processing is ACTIVE, and prompt precisely: "Count the number
of unique individuals traveling on foot (walking/jogging/standing). Count each
person once even if they appear in many frames. Exclude people riding bicycles
or motorcycles and people inside vehicles. Reply with a single integer in
<count></count> tags." Parse the integer from the tagged response. This performs
deduplication implicitly. Use it as a cross-check against the tracking count;
convergence between the two methods increases confidence.

## Output contract reminders
- One sheet exactly named `results`; nothing else.
- Row 1 header strings `filename`, `number` (case-sensitive).
- One data row per video file actually present, sorted alphabetically.
- `number` stored as integer. No empty/summary rows, no extra columns.
- `validate_output.py` checks all of this before you trust the file.
