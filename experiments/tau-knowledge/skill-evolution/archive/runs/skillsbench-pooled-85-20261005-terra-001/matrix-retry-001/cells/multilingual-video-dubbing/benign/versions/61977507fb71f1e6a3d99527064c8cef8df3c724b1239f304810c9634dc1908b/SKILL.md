---
name: broadcast-multilingual-video-dubbing
description: Build a target-language neural-TTS dub from SRT placement windows and a reference target-language SRT. Produces 48 kHz mono normalized segment WAVs, an MP4 that copies the original video stream, and an auditable alignment/loudness report.
---

# Broadcast multilingual video dubbing

Use this Skill for the supplied dubbing inputs: an input MP4, timing-only `segments.srt`, source and reference target SRTs, and a target-language code. It uses the reference target-language text for synthesis; it does not translate the source text. It supports timing-only segment cues with no cue text, because those cues define placement windows rather than dialogue.

The default end-to-end entrypoint is `scripts/run_dubbing.py`. It anchors every utterance at its segment window start, rate-adjusts the utterance to the full window duration, exports 48 kHz mono segment WAVs normalized near -23 LUFS, builds a separately normalized final mix, copies video packets without re-encoding, and measures loudness from the delivered MP4.

## Prerequisites

* `ffmpeg` and `ffprobe` are available on `PATH`. ffmpeg must provide `loudnorm`, `ebur128`, `atempo`, `adelay`, and `amix`.
* An installed Kokoro neural TTS runtime with `KPipeline`, plus `numpy` and `soundfile`, is required. Kokoro must support the requested target language and selected voice.
* `segments.srt`, `source_text.srt`, and `reference_target_text.srt` have the same ordered cue count. Segment cue text may be empty; source and target cue text may not be empty. Every segment window must have positive duration and fit inside the input video.
* The source language is supplied as an ISO 639-1 code. The supplied task uses English, so the end-to-end script defaults to `en`; override this only when the source language is known.

Do not substitute source audio, a tone, or an independent machine translation when neural target-language synthesis is unavailable. Fail clearly instead.

## End-to-end call

The scripts receive one JSON object on stdin and emit one JSON object on stdout. From the runtime work directory, run:

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

The successful call creates all required deliverables:

* `/outputs/tts_segments/seg_0.wav` and one `seg_N.wav` for every additional placement cue;
* `/outputs/dubbed.mp4`;
* `/outputs/report.json`.

Then validate the actual output rather than editing report values manually:

```bash
printf '%s' '{"video":"/outputs/dubbed.mp4","report":"/outputs/report.json","segment_dir":"/outputs/tts_segments"}' | python3 scripts/validate_delivery.py
```

## Processing method

1. Read and trim the ISO target code from `target_language.txt`. The reference target SRT is the sole TTS text source.
2. Use Kokoro's target-language pipeline and a language-appropriate voice to synthesize one raw waveform per target cue.
3. Explicitly downmix/resample each raw waveform to mono 48 kHz, alter tempo to the corresponding placement window duration, and trim/pad exactly to that duration. The report records the original raw TTS duration and `duration_control: "rate_adjust"`.
4. Normalize each delivered segment WAV with a two-pass ITU-R BS.1770 loudness operation targeting -23 LUFS. Place those clips at their exact window starts on a silent timeline.
5. Normalize the complete timeline independently to -23 LUFS, mux it with `-c:v copy`, then measure integrated LUFS from the audio stream in the resulting MP4. Thus the report's `measured_lufs` is a delivered-file measurement, not an intermediate estimate.
6. Preserve report text from the supplied SRTs and calculate drift as `placed_end_sec - window_end_sec`.

## Individual script interfaces

### `run_dubbing.py`

Input fields are `video`, `segments_srt`, `source_srt`, `target_srt`, `target_language_file`, `source_language` (default `en`), `output_dir` (default `/outputs`), and optional Kokoro `voice` and positive `speed`. It returns the output paths and final measured LUFS. It orchestrates synthesis and delivery construction in one process.

### `synthesize_kokoro.py`

Input:

```json
{"text_srt":"PATH","language":"ja","output_dir":"PATH","voice":"OPTIONAL","speed":1.0}
```

It writes ordered `raw_0.wav`, `raw_1.wav`, and so on, and returns `raw_wavs`, the normalized language code, and selected voice.

### `build_dub.py`

Input requires `video`, `segments_srt`, `source_srt`, `target_srt`, `source_language`, `target_language`, and `output_dir`, plus either `raw_wavs` or `raw_wav_dir`. It returns delivered paths and measured loudness. Its JSON report contains all requested global fields and one complete entry per placement window.

### `validate_delivery.py`

Input is `{"video":"PATH","report":"PATH","segment_dir":"PATH","lufs_tolerance":1.0}`. It checks stream format, report consistency, required segment files, start/drift constraints, and independently measured final-video loudness. A failed validation means the media should be rebuilt rather than the report being altered.
