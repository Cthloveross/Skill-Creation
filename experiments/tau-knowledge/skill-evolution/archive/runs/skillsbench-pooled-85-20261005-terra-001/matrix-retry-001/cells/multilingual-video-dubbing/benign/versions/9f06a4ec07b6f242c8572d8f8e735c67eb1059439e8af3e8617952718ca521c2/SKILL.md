---
name: reliable-multilingual-video-dubbing
description: Produce a target-language dubbed MP4, 48 kHz mono segment WAVs, and a measurement-grounded report from an input MP4 plus placement, source, and reference-target SRT files.
---

# Reliable multilingual video dubbing

Use this Skill when an input video, speech-window SRT, source-dialogue SRT, reference target-language SRT, and target-language code are supplied. It creates all required deliverables, while preserving the input video stream rather than re-encoding visual frames.

The reference target SRT is the synthesis script. Do not independently translate the source SRT and do not reuse the source audio as the dub.

## Required runtime

* `ffmpeg` and `ffprobe` must be available on `PATH`.
* `espeak-ng` or `espeak` must be installed for dependable offline synthesis. The default uses it first because it has no model download or network dependency. It is a resilient fallback for constrained environments.
* An installed, locally usable Kokoro installation with its model assets, `numpy`, and `soundfile` is optional. Set `"backend":"kokoro"` only when those assets are known to be locally available; this selects neural TTS.

## Run immediately

The entrypoint reads one JSON object from stdin and emits one JSON object on stdout. Its defaults match the supplied task paths, so this is sufficient:

```bash
printf '%s' '{}' | python3 scripts/run_dubbing.py
```

An explicit invocation is:

```bash
printf '%s' '{
  "video":"/root/input.mp4",
  "segments_srt":"/root/segments.srt",
  "source_srt":"/root/source_text.srt",
  "target_srt":"/root/reference_target_text.srt",
  "target_language_file":"/root/target_language.txt",
  "source_language":"en",
  "output_dir":"/outputs"
}' | python3 scripts/run_dubbing.py
```

Before considering the task complete, confirm that the successful JSON names all of:

* `/outputs/tts_segments/seg_0.wav` (plus one numbered WAV for every later segment),
* `/outputs/dubbed.mp4`, and
* `/outputs/report.json`.

If the entrypoint returns `error`, resolve the named tool or input problem and rerun; do not create a report that declares values not measured from produced media.

## Processing method

1. Parse all SRTs and require matching cue counts. Read target language directly from `target_language.txt` and reference dialogue verbatim from the target SRT.
2. Synthesize each target cue, explicitly downmix/resample it to 48 kHz mono, and time-scale it to its `segments.srt` window. The fitted segment starts exactly at the window start and has zero reported end drift.
3. Normalize each delivered segment and the complete delayed dialogue timeline using FFmpeg BS.1770 `loudnorm` with an integrated target of -23 LUFS.
4. Mux the final normalized timeline with `-c:v copy`, retaining original visual packets/frames and visual timeline. Encode only the new mono 48 kHz audio stream.
5. Probe actual input/output durations and measure delivered MP4 integrated loudness with `ebur128`. Write those measurements, source text, reference target text, windows, placement, and drift into `report.json`.

## Script interfaces

### `scripts/run_dubbing.py`

Input fields are optional when defaults apply: `video`, `segments_srt`, `source_srt`, `target_srt`, `target_language_file`, `source_language` (default `en`), `output_dir` (default `/outputs`), `backend` (`espeak` default or `kokoro`), `voice`, and positive `speed`. It writes all deliverables and returns their paths, target language, selected backend, and measured final MP4 LUFS.

### `scripts/synthesize_speech.py`

Input: `{"text_srt":"PATH","language":"ja","output_dir":"PATH","backend":"espeak","voice":"OPTIONAL","speed":1.0}`. It writes `raw_N.wav` files and returns `raw_wavs`, `language`, `voice`, and `backend`.

### `scripts/build_dub.py`

Input requires `video`, `segments_srt`, `source_srt`, `target_srt`, `source_language`, `target_language`, `output_dir`, and `raw_wavs`. It writes the final WAVs, MP4, and report. It returns only after measuring the delivered MP4.

### `scripts/validate_delivery.py`

Input: `{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","segment_dir":"/outputs/tts_segments"}`. It checks output existence, report timing consistency, audio stream format, delivered duration, and final delivered-video loudness.
