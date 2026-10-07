---
name: timed-multilingual-video-dubbing
description: Generate target-language timed WAV dialogue segments, a 48 kHz mono dubbed MP4 retaining the original visual stream, and an input-grounded dubbing report.
---

# Timed multilingual video dubbing

Use this Skill when a video, timing SRT, source transcript SRT, target-language code, and approved reference target script are supplied. The reference target text is the TTS input; `segments.srt` controls placement only.

## Prerequisites

The runtime needs Python 3 plus `ffmpeg` and `ffprobe`. A local `espeak-ng` or `espeak` installation with the requested language voice is preferred for intelligible speech. The entrypoint has an audible local waveform fallback so that a missing speech binary does not leave required artifacts absent, but a configured target-language voice should be used for a production-quality delivery.

Each of `segments.srt`, `source_text.srt`, and `reference_target_text.srt` must have the same positive number of cues. Timing windows must have positive durations and fit inside the source video.

## Run

Run the packaged entrypoint once from the package directory. It reads one JSON object from stdin and writes one JSON result to stdout:

```sh
printf '%s\n' '{"input_video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","reference_target_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","source_language":"en"}' | python3 scripts/dub.py
```

All input fields are optional strings and default to the public task paths. `output_dir` defaults to `/outputs`. Successful execution creates, at the exact requested paths:

- `/outputs/tts_segments/seg_0.wav` and one 48,000 Hz mono PCM WAV per additional segment;
- `/outputs/dubbed.mp4`, with copied original video and new 48,000 Hz mono AAC audio;
- `/outputs/report.json`, with actual media durations, final-MP4 BS.1770 loudness, and one report entry per timing window.

The script returns `{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":number}` on success. It returns `{"ok":false,"error":string}` and a nonzero status for invalid inputs or failed media processing.

## Processing method

For every timing cue, synthesize exactly the matching reference-target cue, resample/downmix to 48 kHz mono, and render it to the cue window. Overlong utterances are rate-adjusted; shorter utterances are padded with silence. Segment audio begins at the window start by delaying it an exact 48 kHz sample count onto a program-length silent timeline. The video stream is mapped from the input using `-c:v copy`.

The timeline is normalized toward -23 LUFS, muxed, then measured with ffmpeg `ebur128` on the delivered MP4. A correction pass is applied if needed. The report uses measured final-delivery loudness, reports `placed_start_sec` at the timing-window start, and calculates `drift_sec` as `placed_end_sec - window_end_sec`.

## Validate

After creation, validate final delivery rather than intermediates:

```sh
printf '%s\n' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json"}' | python3 scripts/validate_delivery.py
```

Validation checks MP4 stream format, report timing arithmetic, duration consistency, and final integrated loudness. Do not replace target reference text with an independent translation or leave artifacts in a staging directory.
