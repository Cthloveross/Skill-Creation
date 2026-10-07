---
name: timed-multilingual-video-dubbing
description: Create target-language reference-script speech aligned to SRT speech windows, mux it with an unchanged input video stream, and deliver 48 kHz mono WAV/MP4 artifacts and an auditable JSON report.
---

# Timed multilingual video dubbing

Use this Skill for a video plus three corresponding SRT files: timing windows, source transcript, and an approved target-language reference script. The reference target script is the TTS source; do not independently translate the source transcript.

The entrypoint writes these required absolute deliverables directly:

- `/outputs/tts_segments/seg_0.wav` (and one `seg_N.wav` for each additional cue)
- `/outputs/dubbed.mp4`
- `/outputs/report.json`

## Prerequisites

The runtime needs Python 3, `ffmpeg`, and `ffprobe`. If installed, `espeak-ng` or `espeak` is used for local target-language speech synthesis. A deterministic voiced fallback is used only when the local engine cannot render, so media delivery remains possible in an offline runtime. For production-quality speech, install a target-language neural TTS engine or a suitable local voice.

The timing, source, and target SRTs must have equal nonzero cue counts. Timing cues must have positive durations and fit within the input video. `target_language.txt` must contain one two-letter language code.

## Run

`scripts/dub.py` reads one JSON object from stdin and emits a JSON status object to stdout. All task paths have defaults, so `{}` is sufficient in the supplied environment.

```sh
printf '%s\n' '{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "source_language": "en"
}' | python3 scripts/dub.py
```

Successful output has this form:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

Failure output is `{"ok":false,"error":"..."}` with a nonzero exit status.

## Method and output validation

1. Parse window times only from `segments.srt`; pair source and approved target text by cue index.
2. Synthesize the approved target text, explicitly render each delivered segment as a 48,000 Hz mono PCM WAV, and pad or trim it to the exact window duration. It is delayed onto the timeline by its window start in whole 48 kHz samples, making the placement anchor exact and report drift zero.
3. Mix a mono, program-duration dialogue timeline, normalize it toward -23 LUFS with ffmpeg `loudnorm`, copy the original visual stream with `-c:v copy`, and encode a 48 kHz mono AAC audio stream in the MP4. The final MP4 is measured with ffmpeg's BS.1770-compatible `ebur128` filter; a correction pass is applied if necessary.
4. Probe the delivered media before writing the report. The report uses actual container durations, the final-media loudness measurement, the language code read from the input file, verbatim source/reference script text, and drift calculated as `placed_end_sec - window_end_sec`.

The script creates `/outputs` and `/outputs/tts_segments` explicitly and checks that the WAV, MP4, and JSON report exist before success is returned.
