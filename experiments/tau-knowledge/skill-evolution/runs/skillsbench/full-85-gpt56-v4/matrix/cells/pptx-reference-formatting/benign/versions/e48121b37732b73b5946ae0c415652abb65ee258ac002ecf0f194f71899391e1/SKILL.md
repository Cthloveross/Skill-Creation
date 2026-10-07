---
name: pptx-dangling-paper-titles
version: 1.0.0
description: Detect title-like paper names from the content and geometry of a PowerPoint presentation, normalize their formatting and bottom-centered placement, and append a deduplicated numbered Reference slide. Use for .pptx decks containing one or more visually isolated paper titles; it does not rely on slide numbers, shape IDs, or known title text.
---

# Paper-title PowerPoint formatter

Use `scripts/process_presentation.py` to process a supplied `.pptx` presentation. The script discovers candidate paper titles at runtime by examining each slide's text shape content, paragraph structure, placeholder role, font prominence, and nearby text context. It processes at most the strongest qualifying title per source slide, which prevents body paragraphs and caption lists from being treated as titles.

The processor:

1. finds title-like, isolated paper-title text dynamically;
2. converts each selected title to one logical line and formats all its runs as Arial, 16 pt, `#989596`, non-bold;
3. makes the title box as wide as the slide's usable width, disables wrapping, and places it bottom-center;
4. appends one new slide titled `Reference`, containing first-seen unique selected paper titles as automatic numbered bullets; and
5. saves, ZIP-tests, and reopens the resulting package, returning a JSON report.

## Runtime interface

The script reads one JSON object from standard input and emits one JSON object on standard output.

Input schema:

```json
{
  "input": "/absolute/path/source.pptx",
  "output": "/absolute/path/result.pptx",
  "min_score": 5,
  "bottom_margin_inches": 0.22,
  "side_margin_inches": 0.35
}
```

`input` and `output` are required. `min_score` is optional and defaults to `5`; increase it only when the deck has non-paper headings that are incorrectly selected. Margins are optional positive numbers. Input and output must be different paths.

Example:

```sh
printf '%s' '{"input":"/work/source.pptx","output":"/work/result.pptx"}' \
  | python /app/environment/skills/current/scripts/process_presentation.py
```

A successful response has `ok: true`, a nonzero `titles_changed` count, a list of selected titles (for audit), and validation data. `titles_changed: 0` is treated as an explicit failure rather than silently producing a misleading reference slide. Inspect the returned candidate diagnostics if the deck needs a different confidence threshold.

## Assumptions and limits

This is designed for editable PowerPoint text shapes. It cannot identify titles rendered solely into images, drawings without text frames, or external linked content. It intentionally preserves unrelated slides, relationships, media, layouts, themes, and package parts by editing the loaded presentation rather than rebuilding it. The script validates OOXML/package readability but cannot render PowerPoint; for unusually long titles or highly customized template layouts, open the output in PowerPoint as a final visual check.
