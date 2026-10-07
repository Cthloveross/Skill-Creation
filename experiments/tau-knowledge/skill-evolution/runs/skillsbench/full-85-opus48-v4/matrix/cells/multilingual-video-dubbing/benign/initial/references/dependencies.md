# Dependencies and install hints

These are environmental facts to confirm at runtime, not fixed answers.

## Required
- `ffmpeg` and `ffprobe` (loudness via `ebur128`, probing, muxing).
  Check: `ffmpeg -version`.

## TTS backends (first that imports wins)
1. **kokoro** (`from kokoro import KPipeline`) — preferred, native 24 kHz.
   - English pipeline (`lang_code='a'`): needs `misaki[en]`.
   - Japanese pipeline (`lang_code='j'`): needs `misaki[ja]`, `fugashi`,
     and a UniDic dictionary (`unidic` or `unidic-lite`).
   - Install example (only if missing / network allowed):
     `pip install kokoro soundfile misaki[en] misaki[ja] fugashi unidic-lite`
   - Language-code map (ISO 639-1 -> Kokoro): en->a, en-gb->b, ja->j, zh->z,
     es->e, fr->f, hi->h, it->i, pt->p. Default voices live in
     `tts_engine.KOKORO_VOICE`.
2. **kokoro-onnx** (`from kokoro_onnx import Kokoro`) — needs the ONNX model
   and a voices file on disk; `tts_engine` globs for `*kokoro*.onnx` /
   `*voices*.bin`.
3. **espeak-ng** — low-quality fallback; only use if neural TTS is unavailable
   (MOS will likely be poor).

## Quality metric (optional, for validation only)
- **SpeechMOS / UTMOS** via `torch.hub.load('tarepan/SpeechMOS:v1.2.0',
  'utmos22_strong')`. Needs `torch` and network for the first download;
  `librosa` helps resample to 16 kHz mono. UTMOS expects a mono waveform.
  Scores >= ~3.5 are broadcast-acceptable; < 3.0 indicates artifacts.

## Loudness standard
- Target is **-23 LUFS** integrated (ITU-R BS.1770-4 / EBU R128). Always
  re-measure the FINAL mp4 (post AAC encode), not the raw TTS, because
  re-encode/resample/mux can shift integrated loudness by ~0.1-1 LUFS. The
  entrypoint runs a small correction loop and reports the final measurement.

## Format
- Final audio: 48000 Hz, mono. Video stream copied (`-c:v copy`), audio
  encoded (`-c:a aac`). Never copy the audio stream, or the sample rate/channel
  conversion is skipped.
