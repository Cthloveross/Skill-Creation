---
name: pptx-paper-title-reference-formatting
description: Formats role-identified paper-title placeholders on substantive content slides as explicit bottom-centered one-line Arial captions, then appends a deduplicated auto-numbered Reference slide. Use for PPTX decks where titles must be identified from current slide structure rather than slide numbers, text length alone, or shape IDs.
---

# Paper-title formatting and reference slide

This Skill edits a supplied `.pptx` using `python-pptx` and saves a distinct output file. The source deck is not modified.

## Title identification

The script identifies paper titles directly from the source slide OOXML, using the same structural information that is preserved in the presentation package. A paper title is a nonempty `title` or `ctrTitle` placeholder containing at least five normalized characters on a slide with another distinct substantive text shape of at least 20 normalized characters. The companion explanatory shape may be a body/object placeholder or an ordinary text box. This excludes title-only cover pages without relying on fixed slide numbers, title strings, or presentation-specific shape IDs.

Using source OOXML for discovery avoids accidentally treating library-derived or inherited placeholder metadata as a slide-local title role. The selected raw shapes are then mapped to their corresponding editable `python-pptx` shapes by slide-local shape ID.

## Execute

Run `scripts/process_paper_titles.py` with JSON on stdin:

```json
{
  "input_path": "/root/Awesome-Agent-Papers.pptx",
  "output_path": "/root/Awesome-Agent-Papers_processed.pptx"
}
```

Successful stdout is:

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

Invalid JSON, a nonexistent/non-PPTX input, identical source and destination paths, unavailable `python-pptx`, no qualifying title pages, mapping/save errors, or validation errors emit `{ "ok": false, "error": "..." }` and return a nonzero status.

## Transformation

For every selected title, the script replaces the possibly layout-inherited placeholder with a direct-geometry text box. It preserves the normalized title text and gives every nonempty title run explicit OOXML formatting:

- Arial, 16 pt, RGB `#989596`, and non-bold;
- explicit `a:latin typeface="Arial"`, size `1600`, bold false, and solid RGB fill, without relying on a theme or layout;
- one centered paragraph without explicit line breaks or word wrapping;
- full slide width at the bottom center, using the current presentation dimensions.

The script appends exactly one `Reference` slide. Its body lists each selected title once in first-occurrence order, using DrawingML Arabic auto-numbered paragraph bullets.

## Validation

After saving, the script checks ZIP integrity, reopens the deck, confirms the final Reference title and exact ordered entries, and verifies direct title geometry, one-line structure, and explicit raw run formatting. Review the reported `selected` entries for decks with nonstandard title semantics.
