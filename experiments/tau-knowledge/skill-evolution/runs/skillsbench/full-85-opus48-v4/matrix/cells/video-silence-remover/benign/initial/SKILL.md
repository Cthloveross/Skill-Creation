---
name: video-silence-remover
description: >
  Remove the non-teaching opening and long silent pauses from a single teaching
  video (~10 min) and emit a compressed_video.mp4 plus a compression_report.json.
  Use this Skill when the task supplies one lecture/tutorial video and asks to
  (a) remove the static/noise opening, (b) remove long pauses (typically > 2 s),
  (c) keep teaching content, and (d) write a JSON report whose
  original/compressed/removed durations and compression percentage are
  internally consistent. Detection is derived from the actual media (audio
  energy + visual motion); boundaries and thresholds are computed at runtime,
  never hardcoded from any specific recording.
---

# Video Silence Remover

## When to use

The public task gives one input video (e.g. `data/input_video.mp4`) and requires
two deliverables in the current workspace:

1. `compressed_video.mp4` – the input with the opening and long pauses cut out.
2. `compression_report.json` with exactly these fields:
   `original_duration_seconds`, `compressed_duration_seconds`,
   `removed_duration_seconds`, `compression_percentage`, and
   `segments_removed` (a list of `{start, end, duration}` objects, in seconds).

Evaluation checks: files valid; compression rate in a sane range; removed /
compressed duration close to expected; report schema and segment values valid;
and math consistent (`original ≈ compressed + removed`).

## Method (what the script does)

Signals are treated as evidence, decisions are a separate step (see
`references/method.md`). The pipeline, implemented in
`scripts/remove_silence.py`, performs:

1. **Probe** input duration with `ffprobe`.
2. **Audio evidence**: decode to 16 kHz mono PCM, compute per‑frame (50 ms) RMS
   energy in dB, and derive an *adaptive* speech threshold from the recording's
   own noise floor and loudness percentiles (never a fixed cutoff).
3. **Visual evidence** (if NumPy is present): sample low‑resolution grayscale
   frames at a few fps and compute mean absolute frame difference as a motion /
   static signal.
4. **Opening detection**: find the first sustained teaching‑speech onset from
   audio. Because the opening is often *static frames with noise* (loud but
   non‑teaching), also use the visual static→motion transition: if the video is
   clearly static well past the audio onset, extend the opening to the motion
   onset. Safety clamps prevent removing an implausibly large prefix.
5. **Pause detection**: within the content region (after the opening), find
   contiguous low‑energy runs that last at least `min_pause` seconds (default
   2.0 s). Each removal is shrunk by a small margin so teaching speech on either
   side is not clipped.
6. **Serialize intervals as the single source of truth**: build the ordered,
   non‑overlapping *removed* list, derive the complementary *keep* list over
   `[0, duration]`, and build BOTH audio and video from that exact keep list in
   one `ffmpeg` pass using `select`/`aselect` with `setpts=N/FRAME_RATE/TB` and
   `asetpts=N/SR/TB`. Using identical interval expressions for both streams and
   regenerating timestamps keeps audio and video aligned across every join.
7. **Measure and report**: re‑probe the produced file. Report
   `original_duration_seconds` and `compressed_duration_seconds` from the actual
   artifacts, set `removed_duration_seconds = original − compressed` and
   `compression_percentage = removed/original*100` (one rounding policy), so the
   top‑level math is exactly consistent. `segments_removed` lists the planned
   cut intervals (ordered, non‑overlapping, within duration).

The original input file is never modified.

## Running it

The entrypoint reads a JSON config on stdin and writes a JSON result on stdout.

```bash
cd /root   # the workspace / workdir
printf '%s' '{"input":"data/input_video.mp4","output_dir":"."}' \
  | python3 /app/environment/skills/current/scripts/remove_silence.py
```

Config keys (all optional except nothing — sensible defaults apply):
- `input` (string): path to the video. Default tries `data/input_video.mp4`
  then `/root/data/input_video.mp4`.
- `output_dir` (string): where to write outputs. Default: current directory.
- `min_pause` (number, default 2.0): minimum pause length to remove.
- `pause_margin` (number, default 0.15): seconds kept on each side of a pause.
- `min_opening` (number, default 1.5): below this, no opening is removed.
- `preset` (string, default `veryfast`): x264 preset (use `ultrafast` if the
  single‑CPU encode risks exceeding the time budget).

Stdout result includes `report` (the exact JSON written), `output_video`,
`report_path`, diagnostics (`audio_onset`, `visual_onset`, thresholds,
`removed_intervals`, `keep_intervals`), and `warnings`.

The script also writes the two required files directly:
`<output_dir>/compressed_video.mp4` and `<output_dir>/compression_report.json`.

### Validate the result

```bash
printf '%s' '{"report_path":"compression_report.json","input":"data/input_video.mp4","output":"compressed_video.mp4"}' \
  | python3 /app/environment/skills/current/scripts/validate_report.py
```

`validate_report.py` checks schema, numeric types, segment ordering /
non‑overlap / in‑range values, and that `original ≈ compressed + removed`. It
also decodes the output with `ffprobe` to confirm both audio and video streams
exist and that the measured duration matches the reported compressed duration.
It prints `{"ok": bool, "errors": [...], "warnings": [...]}`.

## Executor guidance

1. Confirm `ffmpeg`/`ffprobe` exist (`ffmpeg -version`). NumPy enables the
   visual signal and faster audio math; if it is missing the script falls back
   to an audio‑only, pure‑Python path (still functional, slower).
2. Run `remove_silence.py` from the workspace so outputs land where the task
   expects them. Verify the exported entrypoint actually regenerates both files
   (do not rely on files left by a previous run).
3. Run `validate_report.py`; if `ok` is false, read the `errors`. Common fixes:
   adjust `min_pause`/`pause_margin` if too much/little is removed, lower the
   `preset` to `ultrafast` if the encode is too slow, and re‑run.
4. Inspect diagnostics: if `removed_intervals` is empty, no opening/pause was
   confidently found — prefer keeping content over forcing a cut, but sanity
   check thresholds against the recording. If the warning reports an
   implausibly large opening, the clamp already reduced it; review
   `audio_onset`/`visual_onset`.
5. If `ffprobe` on the output reports a missing stream or a duration far from
   the planned keep total, regenerate (do not edit only the report numbers).

## Failure handling

- Missing input file → the script reports an error and writes no outputs; locate
  the real input path from the task and pass it via `input`.
- No audio stream → audio‑based pause detection cannot run; the script still
  removes a detected static opening and reports the condition in `warnings`.
- Unsupported/empty keep list → the script keeps the whole timeline rather than
  producing an empty video, and records a warning.

See `references/method.md` for the separation of evidence vs. decision rule,
alignment checks, and FFmpeg filter semantics.
