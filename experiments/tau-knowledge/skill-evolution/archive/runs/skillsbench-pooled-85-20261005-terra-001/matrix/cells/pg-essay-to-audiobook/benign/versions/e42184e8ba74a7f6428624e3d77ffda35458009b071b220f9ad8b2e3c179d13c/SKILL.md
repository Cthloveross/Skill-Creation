---
name: web-essay-audiobook
description: Retrieve essays from a publisher index or supplied URLs, extract ordered prose from HTML, synthesize ordered English TTS chunks using OpenAI or ElevenLabs with local-engine fallback, assemble a validated MP3, and write provenance. Use when requested web essays must become one audiobook file.
---

# Web essay audiobook

Use `scripts/audiobook_pipeline.py` to make the artifact. It deliberately separates source retrieval, HTML extraction, synthesis, media-aware assembly, and validation. It does not invent essay text when retrieval fails.

## Runtime requirements

- Python 3 standard library and `ffmpeg`/`ffprobe` must be available.
- Remote retrieval and remote TTS require network access. Source retrieval is essential: a local TTS fallback cannot compensate for unavailable source pages.
- Remote TTS credentials are read only at runtime from `OPENAI_API_KEY` and/or `ELEVENLABS_API_KEY`. `ELEVENLABS_VOICE_ID` is optional; when absent, the script asks ElevenLabs for an available voice.
- Local fallback tries `espeak-ng`, `espeak`, `pico2wave`, then `pyttsx3`. At least one must be installed if remote TTS is unavailable.

## Invocation

Scripts receive one JSON object on stdin and emit one JSON object on stdout. Run:

```bash
python3 scripts/audiobook_pipeline.py <<'JSON'
{
  "titles": ["<first requested essay title>", "<second requested essay title>"],
  "output_path": "/absolute/path/audiobook.mp3",
  "tts_provider": "auto"
}
JSON
```

Input schema:

- `titles` (required unless `sources` is supplied): ordered nonempty list of essay titles. Titles are resolved, in order, from `index_url` (default `https://paulgraham.com/articles.html`).
- `sources` (optional): ordered list of objects with `title` and either `url` or `html`; this is useful when URLs are already known or HTML was supplied through an allowed runtime file/workflow. `html` avoids network retrieval but must be the actual source HTML.
- `output_path` (required): MP3 destination path.
- `index_url` (optional): publisher essay-index URL.
- `tts_provider` (optional): `auto`, `openai`, `elevenlabs`, or `local`; default is `auto`.
- `voice`, `model`, `max_chars`, and `min_duration_seconds` are optional tuning fields. `max_chars` defaults to 3500 and is bounded to 500--4000 for remote OpenAI request safety.

For the requested task, pass the requested titles in the same order as the request and set `output_path` to `/root/audiobook.mp3`. Do not substitute summaries, search snippets, or guessed prose for a failed retrieval.

## Behavior and completion checks

The extractor preserves selected paragraph order and excludes script/style content, direct-link navigation blocks, and common page chrome without paraphrasing prose. It chunks at paragraph/sentence/word boundaries, records an explicit source/chunk order, retries transient HTTP/TTS requests, and uses one selected backend for the whole book when possible.

Each synthesized chunk is decoded and converted to canonical mono WAV before `ffmpeg` concatenates it and encodes the final MP3. The script validates that every requested source yielded content and chunks in order, probes for an audio stream and nontrivial duration, and fully decodes the produced MP3. On success it writes both the MP3 and `<output_path>.manifest.json`; the manifest records source URL, extracted-text hash, chunk order, engine, and measured duration without confusing provenance with generated audio metadata.

A successful stdout object has `ok: true`, `output_path`, `manifest_path`, `duration_seconds`, `engine`, and `sources`. A failure has `ok: false`, a stable `error` category, and a human-readable `message`; do not claim delivery in that case. `source_retrieval_failed` means the executor must restore access to the actual source HTML/URLs rather than attempting TTS on fabricated content.
