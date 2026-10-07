---
name: timed-multilingual-video-dubbing
description: Create an aligned, 48 kHz mono dubbed MP4, per-window TTS WAV files, and an auditable JSON report from an input video, timing SRT, source/reference SRT scripts, and target language code. Use for offline dubbing when ffmpeg and a local TTS backend are available.
---

# Timed multilingual video dubbing

This Skill replaces the input video's audio with synthesized target-language dialogue while copying the original video streams without video re-encoding. It reads timing only from `segments.srt`, uses `reference_target_text.srt` as the TTS text, and uses `source_text.srt` only for report provenance.

## Prerequisites

* `ffmpeg` and `ffprobe` must be on `PATH`; ffmpeg must include `loudnorm` and `ebur128` filters.
* A local TTS backend is required. `auto` first attempts the installed Kokoro Python package (the preferred neural backend), then `espeak-ng`/`espeak` as an availability fallback. For human-quality delivery, install/cache a compatible Kokoro model and its target-language phonemizer, and use `tts_backend: "kokoro"` to fail rather than silently falling back.
* The target language file must contain an ISO 639-1 code (or a recognized language name). The report always writes a normalized ISO 639-1 code.
* This pipeline produces a replacement dialogue track with silence outside dialogue windows. It does not retain the source audio or create a source/dialogue mix.

## Execute

Run `scripts/dub.py` with one JSON object on stdin. All paths are supplied at runtime; no task-specific content is embedded in the Skill.

```json
{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "output_dir": "/outputs",
  "source_language": "en",
  "tts_backend": "kokoro"
}
```

`source_language` defaults to `en` because source language cannot be reliably inferred from arbitrary subtitle text; supply it whenever the source is not English. Optional `kokoro_voice` selects an installed Kokoro voice. With `tts_backend: "auto"`, the program reports the actually selected backend in stdout. `tts_backend` may be `kokoro`, `espeak`, or `auto`.

The entrypoint emits a JSON result on stdout and creates:

* `<output_dir>/tts_segments/seg_0.wav` (and one WAV per additional timing segment), 48 kHz mono;
* `<output_dir>/dubbed.mp4`, with copied video stream(s), AAC 48 kHz mono audio;
* `<output_dir>/report.json` in the requested schema.

For each window, raw TTS duration is preserved as `tts_duration_sec`. Short speech is padded with silence; moderately overlong speech is time-compressed with ffmpeg `atempo`; speech requiring more than 1.5x compression is trimmed. Every rendered clip has the precise window duration, is sample-delayed to the window start, and therefore has zero (apart from floating-point representation) reported end drift. The WAV clips are individually loudness-normalized, then the entire timeline is normalized in a separate two-pass pass. Final LUFS is measured from the AAC audio in `dubbed.mp4`, not an intermediate WAV.

## Validate delivery

After execution, run `scripts/validate_delivery.py` with JSON stdin:

```json
{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json"}
```

It verifies JSON shape and required fields, segment placement/drift tolerances, 48 kHz mono final audio, presence of a video stream, duration sanity, and that the report's final delivered loudness is within 1 LU of -23 LUFS. It emits a JSON success object or a JSON error object and a nonzero exit status.

## Failure handling

The entrypoint fails before writing a claimed deliverable when SRTs contain no usable cues, text cannot be matched to a timing segment, a window is invalid/outside the video, a required executable/filter is absent, no selected TTS backend can synthesize the target text, or probing/muxing fails. Resolve the reported prerequisite or input issue rather than fabricating audio, timing, or loudness values.
