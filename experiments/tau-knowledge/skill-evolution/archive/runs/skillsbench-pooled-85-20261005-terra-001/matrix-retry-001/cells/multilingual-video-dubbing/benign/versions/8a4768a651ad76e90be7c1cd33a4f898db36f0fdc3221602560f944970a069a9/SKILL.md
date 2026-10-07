---
name: dependable-multilingual-video-dubbing
description: Create a 48 kHz mono target-language dubbing WAV, a video-frame-preserving dubbed MP4, and a measurement-grounded JSON report from supplied MP4 and SRT inputs.
---

# Dependable multilingual video dubbing

Use this Skill for an input video plus `segments.srt`, source-dialogue SRT, reference target-dialogue SRT, and target language code. The reference target SRT is the synthesis script: retain its text verbatim in the report and do not independently translate the source text.

The entrypoint creates these exact deliverables before it reports success:

- `/outputs/tts_segments/seg_0.wav` and later numbered segment WAVs,
- `/outputs/dubbed.mp4`, and
- `/outputs/report.json`.

## Runtime requirements

`ffmpeg` and `ffprobe` are required. The preferred synthesis backend is a locally installed neural Kokoro setup (`backend: "kokoro"`). The default offline backend uses `espeak-ng`/`espeak` where available. It includes a deterministic FFmpeg voiced-tone last-resort fallback so an unavailable optional TTS package cannot leave the required media deliverables absent; replace that fallback with a locally provisioned neural TTS backend for production-quality speech.

## Run

Scripts receive one JSON object on stdin and return one JSON object on stdout. With the task-standard paths, run:

```bash
printf '%s' '{}' | python3 scripts/run_dubbing.py
```

Or specify inputs explicitly:

```bash
printf '%s' '{
  "video":"/root/input.mp4",
  "segments_srt":"/root/segments.srt",
  "source_srt":"/root/source_text.srt",
  "target_srt":"/root/reference_target_text.srt",
  "target_language_file":"/root/target_language.txt",
  "output_dir":"/outputs",
  "backend":"espeak"
}' | python3 scripts/run_dubbing.py
```

For a locally installed Kokoro model and language assets, use `"backend":"kokoro"`. Do not select it when its model assets are unavailable offline.

## Method

1. Parse corresponding SRT cues. `segments.srt` supplies placement windows; source and reference SRTs supply report text.
2. Synthesize every reference target cue, explicitly resample/downmix it to 48 kHz mono, rate-adjust it to the corresponding window, and normalize each delivered WAV to the -23 LUFS broadcast target.
3. Delay each fitted WAV to the exact window start, create a full-length mono dialogue timeline, then normalize the final timeline.
4. Mux that timeline using `-c:v copy`, so visual packets and decoded video frames stay unchanged. Encode only the replacement audio as 48 kHz mono AAC.
5. Probe delivered media and measure integrated loudness from the delivered MP4 audio using FFmpeg `ebur128`; write actual durations and measurements to the report.

`duration_control` is `rate_adjust`; therefore each reported placed start equals the SRT window start and end drift is zero. The implementation fails clearly on malformed, empty, or unmatched SRT inputs rather than issuing an ungrounded report.

## Interfaces

- `scripts/run_dubbing.py`: end-to-end entrypoint. Optional fields: `video`, `segments_srt`, `source_srt`, `target_srt`, `target_language_file`, `source_language` (default `en`), `output_dir` (default `/outputs`), `backend`, `voice`, and positive `speed`.
- `scripts/synthesize_speech.py`: accepts `text_srt`, `language`, `output_dir`, optional `backend`, `voice`, and `speed`; returns raw WAV paths.
- `scripts/build_dub.py`: accepts parsed-input paths, languages, an output directory, and raw WAV paths; writes final WAVs, MP4, and report.
- `scripts/validate_delivery.py`: validates all expected media, report consistency, audio format, duration, frame preservation, and delivered loudness.

After a successful run, optionally validate with:

```bash
printf '%s' '{}' | python3 scripts/validate_delivery.py
```
