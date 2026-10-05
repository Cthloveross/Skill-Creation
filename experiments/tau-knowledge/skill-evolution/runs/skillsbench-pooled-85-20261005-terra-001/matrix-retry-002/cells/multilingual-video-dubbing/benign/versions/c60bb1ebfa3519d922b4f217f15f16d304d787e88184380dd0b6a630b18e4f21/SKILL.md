---
name: timed-multilingual-video-dubbing
description: Produce reference-script multilingual dialogue WAVs, a 48 kHz mono dubbed MP4 retaining the original visual stream, and an input-grounded alignment and loudness report.
---

# Timed multilingual video dubbing

Use this Skill for a source video plus a timing-only `segments.srt`, source-text SRT, approved target-script SRT, and target language code. The approved reference target script is the TTS input; do not translate the source script independently. `segments.srt` supplies placement windows and may intentionally contain no cue text.

## Prerequisites

The runtime needs Python 3, `ffmpeg`, and `ffprobe`. The script uses installed `espeak-ng` or `espeak` when available. A deterministic audible fallback is retained so an unavailable local voice does not prevent creation of the required media, though a proper target-language voice is preferred.

All three SRTs must have corresponding positive-duration cues. The timing cues must fit inside the input video.

## Execute

The entrypoint reads one JSON object from stdin and writes one JSON result to stdout. All fields are optional and default to the public task paths.

```sh
printf '%s\n' '{"input_video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","reference_target_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","source_language":"en"}' | python3 scripts/dub.py
```

On success it writes, at the exact selected output root:

- `tts_segments/seg_0.wav` and one additional 48,000 Hz mono PCM WAV per cue;
- `dubbed.mp4`, with copied input video and newly encoded 48 kHz mono AAC audio;
- `report.json`, containing the required global fields and one entry per timing cue.

Successful stdout is:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

Failures emit `{"ok":false,"error":"..."}` and exit nonzero. That is not a deliverable; correct the reported prerequisite or input problem and rerun.

## Processing method

Each target cue is synthesized from the reference-target SRT, explicitly rendered as 48 kHz mono, and duration-controlled to its timing window. Long speech is rate-adjusted; short speech is padded with silence. Every segment is delayed from an exact 48 kHz sample offset corresponding to its requested start, then mixed onto a program-length silent timeline.

The program is loudness-normalized toward -23 LUFS, muxed with `-c:v copy`, and its delivered MP4 audio is measured through FFmpeg's BS.1770-compatible `ebur128` filter. If needed, a bounded correction is applied and remeasured after muxing. The report is produced only after 48 kHz mono output, visual stream presence, finite loudness, and output paths have been checked. `drift_sec` is `placed_end_sec - window_end_sec`.

## Validate

```sh
printf '%s\n' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json"}' | python3 scripts/validate_delivery.py
```

The validator checks the required paths, report numeric/timing arithmetic, final stream format, duration consistency, and final MP4 BS.1770 loudness.