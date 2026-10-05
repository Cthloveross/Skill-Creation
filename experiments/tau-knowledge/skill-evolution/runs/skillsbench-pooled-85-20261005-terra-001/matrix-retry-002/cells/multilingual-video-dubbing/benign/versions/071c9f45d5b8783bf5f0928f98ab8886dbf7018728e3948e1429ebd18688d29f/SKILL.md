---
name: timed-multilingual-video-dubbing
description: Produce the required target-language dubbed MP4, 48 kHz mono segment WAVs, and an alignment/loudness JSON manifest from a video and three supplied SRT files.
---

# Timed multilingual video dubbing

Use this Skill when a supplied reference-language script must replace dialogue on exact SRT timing windows while preserving the input video stream.

The entrypoint reads timing exclusively from `segments.srt`, copies source text from `source_text.srt`, and uses `reference_target_text.srt` verbatim for synthesis. It creates a 48 kHz mono WAV for every timing window, begins each placed WAV at the precise window start, creates a silent replacement-audio timeline matching the source program duration, normalizes the delivered audio toward -23 LUFS, and stream-copies the source video into the delivered MP4.

## Required runtime capabilities

- Python 3 standard library;
- `ffmpeg` and `ffprobe`, including `loudnorm` and `ebur128` filters;
- `espeak-ng` or `espeak`, with a voice usable for the two-letter target ISO language code.

The SRT inputs must have equal nonzero cue counts. Every cue in `segments.srt` must have a positive duration and lie inside the source video. The target-language file must contain exactly one two-letter lowercase or uppercase ISO 639-1 code.

## Execute the public task

The executor must actually run the entrypoint before finishing; merely describing these outputs does not create the required deliverables. From the Skill package directory, run:

```sh
mkdir -p /outputs
printf '%s\n' '{"input_video":"/root/input.mp4","segments_srt":"/root/segments.srt","source_srt":"/root/source_text.srt","reference_target_srt":"/root/reference_target_text.srt","target_language_file":"/root/target_language.txt","output_dir":"/outputs","source_language":"en"}' | python3 scripts/dub.py
```

On success, the command writes all of these exact paths:

- `/outputs/tts_segments/seg_0.wav` (and `seg_N.wav` for subsequent cues): PCM WAV, 48,000 Hz, mono, with the corresponding target reference cue rendered to its timing window;
- `/outputs/dubbed.mp4`: source visual stream copied without re-encoding, plus newly encoded 48 kHz mono AAC dubbed audio;
- `/outputs/report.json`: final-media properties and a segment entry for every window.

Then validate the delivered files, not intermediate media:

```sh
printf '%s\n' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json"}' | python3 scripts/validate_delivery.py
```

## Entrypoint schema

`scripts/dub.py` receives one JSON object on stdin. Its optional string fields are `input_video`, `segments_srt`, `source_srt`, `reference_target_srt`, `target_language_file`, `output_dir`, and `source_language`; defaults are the public task paths shown above. It emits JSON on stdout:

- success: `{"ok":true,"video":"...","report":"...","measured_lufs":number}`;
- failure: `{"ok":false,"error":"..."}` and a nonzero exit status.

`validate_delivery.py` receives `{"video": "path", "report": "path"}` and emits a JSON validation result. It checks report arithmetic, delivered media structure, and integrated loudness measured from the final MP4.

## Timing and report interpretation

Each `placed_start_sec` is the SRT window start. Rendered segment files have the window duration, so their placed end is the window end apart from sample rounding; `drift_sec` is always calculated as `placed_end_sec - window_end_sec`. `tts_duration_sec` records the pre-duration-control synthesized duration. A shorter utterance is padded with silence; a longer utterance is tempo-adjusted while retaining its complete reference-script text.

The report contains the exact source and target cue text from their respective supplied SRTs, target language directly from `target_language.txt`, actual probed input and delivered durations, and the final MP4's measured EBU R128 / BS.1770 integrated loudness.

## Failure behavior

Do not fabricate report values, use the source text as a substitute for the target reference text, or write outputs to a staging directory in place of `/outputs`. If a required tool, TTS voice, input, final stream property, or finite loudness measurement is unavailable, the entrypoint exits with an explicit error. Correct the prerequisite and rerun the command so the three required files exist under `/outputs` before task completion.
