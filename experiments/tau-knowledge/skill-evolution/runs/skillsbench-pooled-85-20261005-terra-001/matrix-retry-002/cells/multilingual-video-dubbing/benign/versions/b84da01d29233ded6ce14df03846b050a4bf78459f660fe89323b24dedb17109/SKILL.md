---
name: timed-multilingual-video-dubbing
description: Create target-reference-script dialogue WAVs, a timeline-aligned 48 kHz mono dubbed MP4 with the original video stream copied, and an auditable dubbing report.
---

# Timed multilingual video dubbing

Use this Skill when an input video, a timing-only `segments.srt`, source transcript SRT, approved target-language reference-script SRT, and target language code are supplied. The reference target script is the synthesis input. Do not independently translate the source transcript.

The Skill writes the required artifacts at the exact public output root `/outputs` by default:

- `/outputs/tts_segments/seg_0.wav` (and one WAV for each additional cue)
- `/outputs/dubbed.mp4`
- `/outputs/report.json`

## Prerequisites

Python 3, FFmpeg, and FFprobe must be installed. `espeak-ng` is preferred and `espeak` is supported as a local speech engine. If neither has a usable target-language voice, the script retains a deterministic voiced fallback so that media production does not silently omit required output; a suitable installed target-language TTS engine should be used whenever available.

All three SRT files must contain the same number of positive-duration cues. Timing windows must end within the input video duration.

## Execute

The entrypoint accepts one JSON object on stdin and returns one JSON object on stdout. All fields below are optional and shown with their public-task defaults.

```sh
printf '%s\n' '{
  "input_video":"/root/input.mp4",
  "segments_srt":"/root/segments.srt",
  "source_srt":"/root/source_text.srt",
  "reference_target_srt":"/root/reference_target_text.srt",
  "target_language_file":"/root/target_language.txt",
  "output_dir":"/outputs",
  "source_language":"en"
}' | python3 scripts/dub.py
```

The program must be run before task completion. It creates `/outputs/tts_segments` itself and writes all three final artifacts directly under the selected output root, rather than leaving them only in a temporary directory. A success result has this schema:

```json
{"ok":true,"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","measured_lufs":-23.0}
```

On an input, synthesis, FFmpeg, or output-path error it emits `{"ok":false,"error":"..."}` and exits nonzero. Such a result is not a completed delivery.

## Method

1. Parse `segments.srt` only for timing windows and pair its cues by index with the source and reference target SRTs.
2. Synthesize each reference-target cue, convert it explicitly to a 48,000 Hz mono PCM WAV, and make its output exactly the cue-window duration. Long speech uses `rate_adjust`; short speech uses `pad_silence`.
3. Delay every segment by an integer 48 kHz sample count equal to its window start, mix those segments onto a silent program-length timeline, then normalize the program toward -23 LUFS.
4. Mux the normalized audio with `-c:v copy` so the video bitstream and visual frames are retained. Audio is encoded as 48 kHz mono AAC. Measure the delivered MP4 using FFmpeg `ebur128`; apply a measured gain correction and remux if required.
5. Write `report.json` only after checking output paths, WAV and MP4 stream formats, duration preservation, copied-video metadata, timing arithmetic, and finite final loudness. `drift_sec` is always `placed_end_sec - window_end_sec`.

## Validate

The validator reads JSON stdin with optional `video`, `report`, `segment`, and `input_video` paths. It checks existence, report schema and arithmetic, MP4/WAV format, duration, final loudness, and that the copied video stream metadata matches the input.

```sh
printf '%s\n' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","segment":"/outputs/tts_segments/seg_0.wav","input_video":"/root/input.mp4"}' | python3 scripts/validate_delivery.py
```
