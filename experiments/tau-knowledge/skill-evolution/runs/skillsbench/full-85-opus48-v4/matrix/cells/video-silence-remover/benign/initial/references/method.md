# Method notes: evidence vs. decision, and alignment

These notes summarize the reusable approach behind the scripts. They are
task-independent; all thresholds and boundaries are computed from the supplied
recording at runtime, never copied from any specific video.

## Separate evidence from the decision rule

No single signal distinguishes teaching from non-teaching. The scripts combine:
- short-time audio energy (per 50 ms frame, in dB) with an adaptive threshold
  derived from the recording's own noise floor (20th pct) and loud level
  (95th pct);
- a visual motion signal (mean absolute difference of low-res grayscale frames)
  to separate a static opening from active content.

Silence detection is candidate generation, not the final classifier. Long
non-speech runs become pause candidates; only runs at least `min_pause` long are
removed, and each is shrunk by a margin to protect adjacent speech.

## Opening vs. pause are different problems

The opening is a contiguous pre-content prefix. It may contain noise, so
digital silence alone cannot identify it; the task note says it is usually
*static frames with noise*. The scripts therefore locate the first sustained
teaching-speech onset AND use the visual static->motion transition: when the
video stays static well past the audio onset, the opening is extended to the
motion onset. A safety clamp refuses to treat more than ~40% of the recording
as opening. Pauses are only sought after the opening, inside confirmed content.

Program onset is a sustained state transition, not the first event. The onset
detector requires speech density to persist over a confirmation window rather
than triggering on an isolated burst.

## Synchronized editing and alignment

Audio and video are rebuilt from the *same* serialized keep list in one pass:
`select`/`aselect` share identical `between(t,...)` interval expressions, and
`setpts=N/FRAME_RATE/TB` / `asetpts=N/SR/TB` regenerate continuous timestamps.
Using one interval list for both streams and re-encoding once keeps samples and
frames aligned across every join, avoiding the per-join drift that occurs when
audio and video are cut with mismatched boundaries.

## Measurement-based report

Input and output durations are measured with `ffprobe` from the actual media.
`removed = original - compressed` and `compression_percentage = removed/original
*100` are derived from those measurements with one rounding policy, so the
top-level math is exactly consistent. `segments_removed` lists the planned cut
intervals (ordered, non-overlapping, within duration). `validate_report.py`
re-checks schema, segment validity, the consistency identity, and that the
produced file decodes with the expected streams and duration. A compression
percentage is an outcome, not a target: the scripts never force a result into a
fixed band, preferring to keep ambiguous content.

## FFmpeg references

Public filter semantics for `trim`, `atrim`, `select`, `aselect`, `setpts`,
`asetpts`, `concat`, and silence-related filters:
https://ffmpeg.org/ffmpeg-filters.html
