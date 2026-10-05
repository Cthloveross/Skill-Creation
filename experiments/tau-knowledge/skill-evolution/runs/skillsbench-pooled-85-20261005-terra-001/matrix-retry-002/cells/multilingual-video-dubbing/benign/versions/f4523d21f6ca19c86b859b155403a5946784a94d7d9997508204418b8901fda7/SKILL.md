---
name: timed-multilingual-video-dubbing
description: Execute an offline dubbing pipeline that reads an input video and SRT scripts, synthesizes the supplied target-language reference text into aligned 48 kHz mono speech, preserves the video stream, and writes the required WAV, MP4, and JSON audit report.
---

# Timed multilingual video dubbing

Use this Skill for the supplied multilingual dubbing task. The executor must run the entrypoint; reading this file alone does not create the deliverables.

The pipeline uses `segments.srt` exclusively for timing, reads source and target dialogue by matching SRT cue ordinal, and synthesizes the target text from `reference_target_text.srt`. It replaces the audio track with dubbed dialogue and silence outside speech windows; it does not mix the original audio into the deliverable.

## Required runtime prerequisites

* `ffmpeg` and `ffprobe` are available on `PATH`. The `loudnorm` and `ebur128` audio filters must be present.
* A local speech backend is available. The default `auto` backend tries installed Kokoro first, then `espeak-ng` or `espeak`. Kokoro is preferred where its target-language model is installed.
* Inputs are readable and each of `segments.srt`, `source_text.srt`, and `reference_target_text.srt` has the same nonzero cue count.

## Execute

Run `scripts/dub.py` once with this JSON on standard input. The listed paths are runtime inputs, not embedded dialogue or instance output values.

```json
{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "output_dir": "/outputs",
  "source_language": "en",
  "tts_backend": "auto"
}
```

The script receives one JSON object on stdin and emits one JSON result on stdout. It creates all required artifacts:

* `/outputs/tts_segments/seg_0.wav` and one similarly named WAV for every additional segment;
* `/outputs/dubbed.mp4` with copied input video and a newly encoded 48,000 Hz mono AAC track;
* `/outputs/report.json` with the required global and per-segment fields.

TTS output is resampled to 48 kHz mono. A short synthesis is padded to its window; a moderately long synthesis is rate-adjusted; an excessively long one is trimmed. The rendered segment length is the SRT window length, so the sample-based timeline placement starts at the window start and reports zero end drift. Final timeline loudness is two-pass normalized toward -23 LUFS and then measured from the muxed MP4 with `ebur128`.

If `auto` selects an unsuitable fallback, install/cache the correct Kokoro language resources and rerun with `"tts_backend":"kokoro"` and, where needed, `"kokoro_voice":"..."`. Do not substitute the source script or independently translated text for the supplied reference target script.

## Validate

After the entrypoint completes, run `scripts/validate_delivery.py` with:

```json
{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json"}
```

The validator emits JSON and exits nonzero for missing/invalid media, non-48-kHz/mono delivery, missing report fields, unacceptable timing arithmetic, or final loudness outside the target range. It is a delivery check and does not synthesize files.

## Failure behavior

The entrypoint fails explicitly rather than claiming a deliverable if required inputs, TTS support, media tools, usable SRT cues, final media probing, or loudness measurement are unavailable. Resolve the prerequisite and rerun the entrypoint. Do not write a report whose timing, dialogue text, duration, or loudness was not obtained from the actual runtime inputs and delivered MP4.
