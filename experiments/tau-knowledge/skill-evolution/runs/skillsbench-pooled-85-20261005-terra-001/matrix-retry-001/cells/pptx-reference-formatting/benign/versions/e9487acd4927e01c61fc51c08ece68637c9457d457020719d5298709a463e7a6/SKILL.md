---
name: pptx-paper-title-reference-formatting
description: Formats role-identified paper-title placeholders on substantive content slides as explicit bottom-centered one-line Arial captions, then appends a deduplicated auto-numbered Reference slide. Use for PPTX decks where titles must be identified from current slide structure rather than slide numbers, text length, or shape IDs.
---

# Paper-title formatting and reference slide

This Skill edits a supplied `.pptx` using `python-pptx` and saves a distinct output file. It leaves the source deck unchanged.

## Title identification

A paper page is discovered at runtime when it has a nonempty `title` or `ctrTitle` placeholder and at least one *other*, nonidentical substantive text shape (20 or more characters). The companion explanatory shape may be a body/object placeholder or an ordinary text box. This excludes title-only cover slides without relying on fixed slide numbers or title text length.

## Execute

Run `scripts/process_paper_titles.py` with JSON on stdin:

```json
{
  "input_path": "/root/Awesome-Agent-Papers.pptx",
  "output_path": "/root/Awesome-Agent-Papers_processed.pptx"
}
```

The script emits a JSON object on stdout. Successful output has this schema:

```json
{
  "ok": true,
  "output_path": "...",
  "titles_detected": 0,
  "unique_titles": 0,
  "selected": [{"slide": 1, "text": "..."}],
  "validation": {
    "zip_ok": true,
    "reopen_ok": true,
    "reference_slide_ok": true,
    "titles_ok": true
  }
}
```

Invalid JSON, nonexistent/non-PPTX input, an identical input/output path, unavailable `python-pptx`, no qualifying title pages, save errors, or validation errors produce `{ "ok": false, "error": "..." }` and a nonzero exit status.

## Transformation

Each selected title placeholder is replaced with a direct-geometry text box. This avoids relying on title geometry inherited only from a slide layout. The replacement preserves the title’s logical text and is explicitly configured as follows:

- Arial, 16 pt, RGB `#989596`, and non-bold on every nonempty run;
- explicit OOXML run properties, including `a:latin typeface="Arial"`, rather than theme inheritance;
- one normalized paragraph with no explicit line breaks, centered and non-wrapping;
- full slide width at the bottom center, derived from the presentation’s own dimensions.

One `Reference` slide is appended at the end. It contains each unique normalized title once, preserving first-occurrence order, with OOXML Arabic auto-numbered body paragraphs.

## Validation

The script tests ZIP integrity, reopens the output presentation, confirms the final Reference title and exact numbered entries, and validates each rewritten title’s direct geometry, one-line structure, and raw explicit OOXML font properties. Review `selected` if a deck has nonstandard title semantics.
