# Chapter alignment cues (method reference, not instance answers)

These notes summarize the domain rules the scoring and repair logic implement.
They describe *how* to align generic tutorial chapters; they contain no
timestamps or answers for any particular video.

## Core rule
- A chapter's timestamp is where the speaker FIRST BEGINS SUSTAINED discussion /
  work on the topic, not a passing earlier mention and not every later mention.
- Chapter titles are human summaries, rarely spoken verbatim -> use fuzzy
  keyword/semantic matching, never plain substring search.

## Structural invariants to enforce (from the output schema)
- chapters length == number of expected titles.
- titles reproduced character-for-character (apostrophes, `!`, capitalization).
- time is numeric seconds.
- strictly monotonically increasing (no ties).
- first chapter time == 0.
- all times within [0, duration].

## Why global ordering matters
- Independent best-match per title can produce non-monotonic times (a vague
  title matching an earlier segment). A monotonic DP + repair pass guarantees
  the final sequence is strictly increasing.

## Duration/archetype expectations (tie-breaking prior only)
- Intro / overview chapters at the start: short.
- Core procedure chapters in the middle: long.
- Utility actions (Save, Break): very short, may occupy part of one segment.
- Closing/outro: short.
- The 'Break' + 'Continue' pattern: a very short interruption between two
  segments of the same topic; the break is a brief step back from the procedure.
- These expectations only break ties via a small positional prior; the dominant
  signal is transcript keyword/semantic evidence.

## ASR caveats
- Whisper segment boundaries approximate, not exact, topic transitions.
- Technical/proper nouns (software names, tool names) are often misrecognized;
  fuzzy matching with a threshold (~0.8) absorbs these errors.
- Prefer faster-whisper int8 on CPU for speed; openai-whisper is a fallback.
- A larger model (small > base > tiny) gives cleaner keywords for alignment.
