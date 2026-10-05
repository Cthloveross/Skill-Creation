---
name: timed-multilingual-video-dubbing
description: Create a target-language dubbed MP4 from an input video, segment timing SRT, source script, and supplied reference target script. Produces 48 kHz mono segment WAVs, a video-copy MP4, and an auditable alignment/loudness report.
---

# Timed multilingual video dubbing

Use this Skill to execute the supplied dubbing task. The executor must run the entrypoint; this package does not itself create media until executed.

The pipeline reads timing only from `segments.srt`, copies source text from `source_text.srt`, and uses `reference_target_text.srt` verbatim as the TTS input. It creates one 48 kHz mono WAV per timing window, places each WAV exactly at its window start on a silent replacement-audio timeline, normalizes the final timeline toward EBU R128 / BS.1770 integrated loudness, and muxes that audio with a copied video stream.

## Prerequisites

The runtime must provide:

- `ffmpeg` and `ffprobe`, including the `loudnorm` and `ebur128` filters;
- `espeak-ng` or `espeak` with a voice for the ISO language code in `target_language.txt`.

The three SRT files must contain equal, nonzero cue counts. The target-language file must contain a two-letter ISO 639-1 code. The supplied paths are defaults and are read only at execution time.

## Execute

Run `scripts/dub.py` with one JSON object on stdin. For the public task, use:

```json
{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "output_dir": "/outputs",
  "source_language": "en"
}
```

The script emits a JSON result on stdout. On success it writes:

- `/outputs/tts_segments/seg_0.wav`, plus `seg_N.wav` for later windows. Every WAV is PCM, mono, 48,000 Hz, has the exact window duration, and contains TTS derived from the corresponding reference target cue.
- `/outputs/dubbed.mp4`, containing the original copied video stream and newly encoded 48,000 Hz mono AAC dubbed audio.
- `/outputs/report.json`, containing global delivered-media measurements and one alignment record per segment.

Each placed segment begins at its SRT window start. Its rendered duration is constrained to the window duration, so `placed_end_sec` equals `window_end_sec` and `drift_sec` is zero apart from sample rounding. The final MP4, rather than an intermediate WAV, is measured with `ebur128`; if needed, a final gain correction is remuxed and measured again.

## Input and output schema

`dub.py` accepts a JSON object with optional string fields `input_video`, `segments_srt`, `source_srt`, `reference_target_srt`, `target_language_file`, `output_dir`, and `source_language`. Defaults are the public task paths above. It writes `{"ok":true,"video":"...","report":"...","measured_lufs":number}` on success. On failure it writes `{"ok":false,"error":"..."}` and exits nonzero.

## Validate

After generation, run `scripts/validate_delivery.py` with:

```json
{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json"}
```

It emits JSON and exits nonzero if the files are missing, report structure or timing arithmetic is invalid, the delivered audio is not 48 kHz mono, or measured final loudness is outside the normal broadcast tolerance.

## Failure behavior

Do not fabricate a report or substitute the source script for the reference target script. If a required file, media tool, TTS voice, or final loudness measurement is unavailable, the entrypoint fails explicitly before reporting success. Resolve that prerequisite and rerun the entrypoint.
