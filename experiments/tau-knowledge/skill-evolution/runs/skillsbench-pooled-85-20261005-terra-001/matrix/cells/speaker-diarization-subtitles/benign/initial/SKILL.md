---
name: diarized-video-to-rttm-ass-report
description: Generate evidence-based speaker diarization, speaker-prefixed ASS subtitles, and a reproducible JSON report from a video containing speech. Use when the source video is available locally and the runtime has ffmpeg, NumPy, a usable SpeechBrain speaker-embedding model, and a usable Whisper-compatible ASR model.
---

# Diarized video to RTTM, ASS, and report

This Skill creates three mutually consistent artifacts from a video:

- an RTTM whose speaker turns are derived from acoustic speech detection and speaker embeddings, not ASR timing;
- an ASS subtitle file with `SPEAKER_XX:` in every dialogue line and ASS centisecond timestamps;
- a JSON report containing actual successful components and derived statistics.

The packaged pipeline first extracts one 16 kHz mono PCM WAV. It detects acoustically active speech from that same WAV, obtains SpeechBrain ECAPA speaker embeddings for VAD-derived speech windows, clusters embeddings, merges only contiguous same-speaker windows, and transcribes those final acoustic speaker turns. Thus, ASR produces text only and is not used as the RTTM temporal authority.

## Prerequisites and runtime discovery

Before running, inspect the runtime rather than assuming a particular installation:

```bash
command -v ffmpeg
python3 -c 'import numpy, torch, speechbrain; print("speaker embedding dependencies available")'
python3 -c 'import faster_whisper; print("faster-whisper available")' \
  || python3 -c 'import whisper; print("openai-whisper available")'
```

The input video must be readable by ffmpeg. The runner can download the public SpeechBrain ECAPA model and the requested ASR model into its work directory when network access is available; it also uses already cached models normally. Do not fabricate an all-duration RTTM when an embedding model or ASR model is unavailable. Resolve the missing prerequisite or use an installed, validated diarization/ASR implementation, then use `validate_outputs.py` on its artifacts.

## Execute

The scripts receive one JSON object on stdin and emit one JSON result on stdout. From the package root, for the supplied task input:

```bash
python3 scripts/run_diarization.py <<'JSON'
{
  "input_video": "/root/input.mp4",
  "rttm_path": "/root/diarization.rttm",
  "subtitles_path": "/root/subtitles.ass",
  "report_path": "/root/report.json",
  "file_id": "input",
  "asr_model": "base"
}
JSON
```

### Runner input schema

- `input_video` (required string): local video/audio path.
- `rttm_path`, `subtitles_path`, `report_path` (required strings): output paths.
- `file_id` (optional string, default `input`): RTTM recording ID.
- `work_dir` (optional string): directory for extracted WAV and model caches.
- `asr_model` (optional string, default `base`): a model identifier supported by the installed faster-whisper or openai-whisper package.
- `language` (optional string or null): ASR language hint. Omit/null for automatic detection.
- `max_turn_sec` (optional positive number, default `1.5`): maximum VAD speech window used for local speaker evidence. Lowering it can improve change resolution but makes embeddings less reliable.

The result is `{"ok": true, "outputs": ..., "validation": ...}` on success. On a prerequisite or processing failure it is `{"ok": false, "error": ...}`. A failure is intentional: it prevents plausible-looking files with unsupported speaker identities or invented transcript text.

## Interpretation and quality control

The runner selects one or more speakers from the recording's embedding geometry (silhouette comparison) and labels final RTTM speakers `spk00`, `spk01`, etc. The ASS mapping is deterministic: `spk00 -> SPEAKER_00`. A one-speaker outcome is permitted only when the embedding evidence does not support a stable split; it is never created as a whole-recording fallback.

The adaptive energy detector is an acoustic VAD fallback suitable for environments lacking a dedicated neural VAD, but it can be unreliable with music, heavy noise, or overlapping speech. For those recordings, an executor should run a validated installed VAD/diarization system, retain its independently derived RTTM, transcribe its turns, and validate the resulting three artifacts. Do not copy ASR segment times into RTTM.

Validate generated or externally produced artifacts with:

```bash
python3 scripts/validate_outputs.py <<'JSON'
{
  "rttm_path": "/root/diarization.rttm",
  "subtitles_path": "/root/subtitles.ass",
  "report_path": "/root/report.json"
}
JSON
```

Validation checks RTTM field count/type, nonnegative starts and positive durations, ASS header/timestamp/dialogue structure, speaker-label linkage, report schema and statistics, and one-to-one cue/turn timing correspondence. Inspect the report's `notes` for explicitly marked untranscribed turns; `[untranscribed]` means ASR returned no text for an acoustically detected turn and is not a claimed transcript.
