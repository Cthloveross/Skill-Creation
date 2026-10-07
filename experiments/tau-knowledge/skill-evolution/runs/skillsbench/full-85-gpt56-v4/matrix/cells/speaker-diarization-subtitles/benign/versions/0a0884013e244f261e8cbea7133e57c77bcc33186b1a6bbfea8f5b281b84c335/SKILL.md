---
name: diarized-video-subtitles
version: 1.0.0
description: Create validated RTTM diarization, speaker-prefixed ASS subtitles, and a reproducibility report from a video using the best locally available ASR and diarization backends. Use for video/audio diarization tasks requiring internally consistent temporal artifacts.
---

# Diarized video subtitles

Run `scripts/diarize_video.py` with a JSON object on stdin. It extracts a single, 16 kHz mono PCM WAV source, attempts available diarization and ASR backends, aligns recognized text to diarization turns by temporal overlap, and writes RTTM, ASS, and report artifacts.

## Runtime prerequisites and backend selection

Before running, inspect the environment rather than assuming a model is installed:

```sh
command -v ffmpeg; command -v ffprobe
python3 - <<'PY'
import importlib.util
for x in ('pyannote.audio', 'speechbrain', 'faster_whisper', 'whisper', 'sklearn', 'torch'):
    print(x, bool(importlib.util.find_spec(x)))
PY
```

`ffmpeg` and `ffprobe` are mandatory. The script uses this ordered backend policy:

1. A locally usable `pyannote.audio` speaker-diarization pipeline, when its model is available and any required Hugging Face token is supplied in `HF_TOKEN`.
2. `speechbrain` ECAPA embeddings clustered over independently detected speech intervals. Embeddings are evaluated in padded batches with bounded acoustic context, retaining the original VAD intervals as turn boundaries. Average-cosine linkage chooses a compact silhouette-supported partition only when repeated embedding evidence supports it.
3. Energy-based VAD intervals with one explicitly documented fallback speaker **only if no speaker model can run**. This is not an all-recording fallback: silence is excluded and the report records the limitation.

For ASR it prefers `faster-whisper`, then OpenAI `whisper`. If neither is installed, install one in the task environment (for example `pip install faster-whisper`) and rerun. Models may download only where task network policy permits. Do not claim a backend in the report unless it actually completed.

The optional `HF_TOKEN` must be authorized for the selected pyannote model. A failed or gated pyannote load is safely skipped in favor of the next backend.

## Invocation

The script receives one JSON object on standard input and emits a JSON execution summary on standard output. Paths may be changed for a different task; all output paths are explicit.

```sh
python3 /app/environment/skills/current/scripts/diarize_video.py <<'JSON'
{
  "input_video": "/root/input.mp4",
  "rttm_output": "/root/diarization.rttm",
  "ass_output": "/root/subtitles.ass",
  "report_output": "/root/report.json",
  "file_id": "input",
  "asr_model": "small",
  "pyannote_model": "pyannote/speaker-diarization-3.1"
}
JSON
```

`asr_model` is passed only to the ASR backend that actually runs. The default `small` model is selected when it is locally cached for a CPU-only English runtime; provide a cached or otherwise feasible alternative only after accounting for the task time budget. The input audio is never re-timed after extraction.

## Outputs and method

* RTTM has exactly ten fields per `SPEAKER` record, nonnegative starts, positive durations, and normalized `spk00`, `spk01`, ... identities.
* ASS is a complete ASS document. Every emitted dialogue cue takes its start/end from an RTTM turn and uses `SPEAKER_XX: ` followed by recognized text. ASS times are centiseconds (`H:MM:SS.cc`).
* A recognized phrase is assigned by aggregate positive overlap to a speaker cluster and its supporting VAD regions. The final RTTM/ASS cue takes the first and last supporting VAD boundary, never ASR decoder boundaries. A decoder segment just outside a VAD edge may use the nearest turn only within 0.60 seconds; unsupported decoder text is discarded.
* `report.json` is calculated from the written RTTM and probed audio duration. It includes actual completed steps, commands, imported libraries, selected tools, model parameters, and any fallbacks/errors.

The report intentionally counts the sum of RTTM turn durations as `total_speech_time_sec`; overlapping diarization turns therefore contribute separately, which is the direct RTTM-duration definition. The `num_speakers_pred` value is the number of final RTTM labels.

## Validation

The entrypoint validates all generated artifacts before declaring success: RTTM field count/type/timing, ASS dialogue timing and `SPEAKER_XX:` prefixes, JSON required fields, report-to-RTTM speaker count, report-to-RTTM duration total, and report audio duration. A validation failure exits nonzero rather than leaving a success claim. Inspect `report.json` for the actual fallback or model errors before relying on low-confidence output.
