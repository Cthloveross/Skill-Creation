---
name: pptx-paper-title-reference-formatting
description: Detects likely standalone paper-title shapes in a PowerPoint deck, formats and repositions them as bottom-centered one-line captions, and appends a deduplicated numbered Reference slide. Use for presentation-wide paper-title cleanup where titles must be identified from each slide's current shapes rather than fixed slide numbers or object IDs.
---

# Paper-title formatting and reference slide

This Skill edits a supplied `.pptx` with `python-pptx`. It never changes the input file; it writes a separate output presentation.

## Detection approach

Paper-title detection is necessarily semantic. The script discovers all text shapes at runtime, gives strong preference to title/center-title placeholders, and otherwise selects the most title-like standalone one-line text box on each populated slide. It excludes obvious URLs, citation-like text, list items, and paragraph-heavy body content. It reports the selected titles, slide numbers, shape names, and low-confidence selections so an executor can inspect or refine any ambiguous deck.

The default `primary_per_slide` behavior intentionally selects at most one title per pre-existing slide. This avoids treating every line in an abstract, table, or bibliography as a paper title. If a deck has more than one standalone paper title on a slide, use `selection_mode: "all_standalone"` and review the report.

## Runtime requirements

- Python with `python-pptx` installed.
- Read access to the input `.pptx` and write access to the requested output path.
- No PowerPoint application is required, but application-level visual review is recommended for unusually long titles because font metrics vary by installed Arial version.

## Execute

Run `scripts/process_paper_titles.py` with a JSON object on stdin. Example payload (paths are supplied by the task, not embedded in the Skill):

```json
{
  "input_path": "/root/Awesome-Agent-Papers.pptx",
  "output_path": "/root/Awesome-Agent-Papers_processed.pptx",
  "selection_mode": "primary_per_slide"
}
```

The script emits one JSON object on stdout:

```json
{
  "ok": true,
  "output_path": "...",
  "titles_detected": 0,
  "unique_titles": 0,
  "selected": [{"slide": 1, "shape": "...", "text": "...", "confidence": "high"}],
  "warnings": [],
  "validation": {"zip_ok": true, "reopen_ok": true, "reference_slide_ok": true}
}
```

On invalid arguments, missing dependencies, unreadable input, no detected titles, or a validation failure, it emits `{ "ok": false, "error": "..." }` and exits nonzero. A no-title result is treated as a failure rather than silently appending an empty reference slide.

## What the script changes

For every selected existing title it:

1. applies Arial, 16 pt, RGB `989596`, and non-bold formatting to every existing run;
2. disables wrapping, normalizes accidental line-break whitespace to spaces, gives the shape the usable slide width, and horizontally centers its paragraph(s);
3. places the title box at the bottom center using actual slide dimensions and its existing height.

It then appends a new slide containing a `Reference` title and a body text box with deduplicated detected titles as OOXML automatic Arabic numbered paragraphs. Duplicate comparison is case-insensitive and whitespace/punctuation-insensitive, while the first encountered spelling is retained for display.

The script uses no fixed slide index, shape identifier, paper title, slide dimensions, or layout index. It preserves the original deck and writes a new package, but `python-pptx` can normalize unsupported OOXML constructs; therefore, inspect output in PowerPoint for decks containing unusual embedded objects, macros, or custom XML.

## Validation and ambiguity handling

After saving, the script checks ZIP integrity, reopens the resulting presentation, confirms that the final slide has the expected title and numbered body entries, and checks selected title shapes for required run formatting and bottom-center placement. Review `selected` and `warnings`. If selection is semantically incorrect, use the reported candidate text/shape information to adjust the presentation source or rerun with `selection_mode: "all_standalone"`; do not hard-code source slide IDs into this Skill.
