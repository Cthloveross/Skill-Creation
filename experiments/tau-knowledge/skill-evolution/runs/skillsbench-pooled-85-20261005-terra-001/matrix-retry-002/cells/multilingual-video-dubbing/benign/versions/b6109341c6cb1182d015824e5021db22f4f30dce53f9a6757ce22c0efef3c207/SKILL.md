---
name: timed-multilingual-video-dubbing
description: Produce target-reference-script speech WAVs, a 48 kHz mono dubbed MP4 retaining the input visual stream, and a timing/loudness report from timing and transcript SRT inputs.
---

# Timed multilingual video dubbing

Use this Skill for a video with a timing-only `segments.srt`, source transcript SRT, approved target-language reference-script SRT, and a two-letter target language code. The approved reference script is the TTS input; do not independently translate source text.

The executable creates the required artifacts directly at the public output root by default:

- `/outputs/tts_segments/seg_0.wav` (and `seg_N.wav` for every further cue)
- `/outputs/dubbed.mp4`
- `/outputs/report.json`

## Prerequisites

The runtime needs Python 3, FFmpeg, and FFprobe. `espeak-ng` is preferred, with `espeak` supported as a local offline synthesis fallback. When neither engine can render the requested language, the program uses a deterministic audible fallback rather than silently delivering silence; this fallback is not a substitute for a suitable target-language neural TTS installation.

All three SRT files must have the same positive-duration cue count. Timing windows must fit within the source video.

## Run

`scripts/dub.py` reads one JSON object from stdin and emits one JSON object on stdout. Run it before completing the task; it creates `/outputs/tts_segments` and writes final files at the requested absolute paths, not merely to a staging directory.

```sh
printf '%s\n' '{
  "input_video": "/root/input.mp4",
  "segments_srt": "/root/segments.srt",
  "source_srt": "/root/source_text.srt",
  "reference_target_srt": "/root/reference_target_text.srt",
  "target_language_file": "/root/target_language.txt",
  "output_dir": "/outputs",
  "source_language": "en"
}' | python3 scripts/dub.py
```

All fields have the shown defaults. On success stdout is:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

On a prerequisite, input, synthesis, media, or output-path error, stdout is `{"ok":false,"error":"..."}` and the process exits nonzero. That result is not a completed delivery.

## Processing method

1. Parse timing only from `segments.srt`; pair cues by index with `source_text.srt` and `reference_target_text.srt`.
2. Synthesize the reference target text, explicitly convert it to a PCM, mono 48,000 Hz WAV, and duration-control it to its cue window. Overlong speech uses `rate_adjust`; shorter speech is retained and padded with silence.
3. Place each WAV with a sample-accurate delay equal to the cue start, mix on a silent source-duration timeline, and normalize the program toward -23 LUFS.
4. Mux that audio with `-c:v copy`, preserving the input visual bitstream. The output audio is explicitly AAC encoded at 48 kHz mono. Measure the delivered MP4 with FFmpeg `ebur128`, apply an encoded-output loudness correction when needed, and measure again.
5. Probe generated media before writing `report.json`. The report records actual media durations, final MP4 loudness, reference/source text, and `drift_sec = placed_end_sec - window_end_sec`.

The script rejects delivery if final MP4 audio is not 48 kHz mono, its video metadata differs from the copied input stream, its timeline differs materially from the input, or final integrated loudness cannot be brought near -23 LUFS.

## Validate an existing delivery

The entrypoint performs delivery validation itself. For an independent structural check, run:

```sh
printf '%s\n' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","segment":"/outputs/tts_segments/seg_0.wav"}' | python3 scripts/validate_delivery.py
```

The validator emits JSON, checks required paths, 48 kHz mono WAV/MP4 streams, required report fields and placement arithmetic, and verifies that the report loudness is a finite numeric value. Use FFmpeg `ebur128` on the final MP4 when auditing broadcast loudness independently.
