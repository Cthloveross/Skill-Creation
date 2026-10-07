---
name: pptx-paper-title-reference-formatting
description: Formats paper-title placeholders on content slides as bottom-centered one-line Arial captions and appends a deduplicated auto-numbered Reference slide. Use when paper titles are identified by their title-placeholder role and accompanying substantive body content, not by fixed slide numbers, text length, or object identifiers.
---

# Paper-title formatting and reference slide

This Skill edits a supplied `.pptx` with `python-pptx` and writes a distinct output file. It preserves the source deck unchanged.

## Title identification

A paper page is identified at runtime as a slide containing:

- a nonempty `title` or `ctrTitle` placeholder; and
- a distinct `body` or `obj` placeholder/text shape with at least 20 characters of explanatory content.

This role-based rule excludes a title-only cover and does not mistake abstracts or long descriptions for paper titles. When several title-role shapes exist, the nonempty longest title-role shape is used, matching the presentation's title-placeholder semantics.

## Execute

Run `scripts/process_paper_titles.py` with JSON on stdin:

```json
{
  "input_path": "/root/Awesome-Agent-Papers.pptx",
  "output_path": "/root/Awesome-Agent-Papers_processed.pptx"
}
```

The script emits one JSON object on stdout. On success:

```json
{
  "ok": true,
  "output_path": "/root/Awesome-Agent-Papers_processed.pptx",
  "titles_detected": 0,
  "unique_titles": 0,
  "selected": [{"slide": 1, "text": "..."}],
  "validation": {"zip_ok": true, "reopen_ok": true, "reference_slide_ok": true, "titles_ok": true}
}
```

On invalid JSON, invalid paths, missing `python-pptx`, no qualifying paper-title pages, or output validation failure, it emits `{ "ok": false, "error": "..." }` and exits nonzero.

## Transformation

For each identified title, the script replaces the selected title placeholder with an explicit text box. This is intentional: placeholders can inherit geometry solely from a layout and therefore lack usable slide-level transform geometry after editing. The replacement preserves the logical title text while giving it direct geometry.

Each replacement title is:

- Arial, 16 pt, RGB `#989596`, with bold explicitly disabled on every run;
- one paragraph with normalized whitespace and no explicit line breaks;
- non-wrapping and centered;
- full slide width and directly positioned at the bottom center using the deck's actual slide dimensions.

The script appends exactly one slide. It adds a `Reference` title and one auto-numbered OOXML Arabic paragraph per unique paper title. Deduplication is exact after whitespace normalization, retaining the first encountered spelling; this avoids incorrectly collapsing genuinely distinct titles that differ only in punctuation or capitalization.

## Validation

After saving, the script verifies ZIP integrity, reopens the presentation, confirms the final slide has `Reference` plus the expected auto-numbered entries, and checks every replacement title's direct geometry, single-paragraph form, and explicit run formatting. Inspect the returned `selected` list if the deck uses nonstandard layouts or has no title/body placeholder structure.
