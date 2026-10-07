---
name: reliable-multilingual-video-dubbing
description: Produce a target-language 48 kHz mono dubbed WAV, a frame-preserving MP4, and a measurement-grounded alignment report from an MP4 plus placement, source, and reference-target SRT files.
---

# Reliable multilingual video dubbing

Use this Skill for an input video, a placement-window SRT, source and reference target scripts, and a target-language code. The reference target SRT is the synthesis input. Do not replace it with an independent translation.

The end-to-end script creates:

- `/outputs/tts_segments/seg_0.wav` (and one `seg_N.wav` per additional cue),
- `/outputs/dubbed.mp4`, with the source video stream copied unchanged, and
- `/outputs/report.json`.

## Prerequisites

`ffmpeg` and `ffprobe` must be available. The default offline speech backend is `espeak-ng` or `espeak`; it is selected for delivery reliability. A locally provisioned Kokoro installation may be selected explicitly with `"backend":"kokoro"` for neural target-language synthesis. If an offline speech program cannot synthesize the requested language, the script uses an audible FFmpeg fallback so it does not silently omit required artifacts. Provision a local neural TTS backend for production human-quality results.

## Run

Scripts receive one JSON object on stdin and emit one JSON object on stdout. From the package directory, run the standard task paths with:

```bash
printf '%s' '{}' | python3 scripts/run_dubbing.py
```

An explicit call is:

```bash
printf '%s' '{"video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","target_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","backend":"espeak"}' | python3 scripts/run_dubbing.py
```

The entrypoint validates inputs, creates `/outputs` and `/outputs/tts_segments`, synthesizes each target cue, rate-fits it exactly to the corresponding window, normalizes segment and final dialogue audio near -23 LUFS, copies the input video stream into the MP4, and writes a report from actual probes and final-file loudness measurement.

## Alignment and report method

- `segments.srt` controls placement windows; source and target SRTs provide report text in matching cue order.
- Each cue starts at the exact window start and is rate-adjusted, then padded or trimmed to the window duration. Consequently the reported placement end is the window end and `drift_sec` is zero.
- Delivered WAV and MP4 audio are explicitly 48,000 Hz mono.
- Final integrated loudness is measured from the delivered MP4 audio with FFmpeg `ebur128`, not copied from an intermediate measurement.
- The report uses actual input and output durations, supplied language codes and text, and `drift_sec = placed_end_sec - window_end_sec`.

The pipeline rejects malformed/empty SRTs, differing cue counts, missing source media, and windows outside the input visual timeline instead of producing an ungrounded report.

## Script interfaces and validation

- `scripts/run_dubbing.py`: complete workflow. Optional fields: `video`, `segments_srt`, `source_srt`, `target_srt`, `target_language_file`, `source_language`, `output_dir`, `backend`, `voice`, and positive `speed`.
- `scripts/synthesize_speech.py`: accepts `text_srt`, `language`, and `output_dir`, plus optional `backend`, `voice`, and `speed`; returns raw cue WAV paths.
- `scripts/build_dub.py`: accepts video/SRT paths, language codes, `output_dir`, and `raw_wavs`; creates delivery artifacts.
- `scripts/validate_delivery.py`: checks all delivery artifacts and returns `{ "ok": bool, "errors": [...], "measured_lufs": number|null }`.

After the main script returns successfully, validate the delivered paths with:

```bash
printf '%s' '{}' | python3 scripts/validate_delivery.py
```
