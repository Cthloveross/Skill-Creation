---
name: blind-pdf-anonymization
description: Create faithful, anonymized PDFs for blind peer review from supplied academic PDFs. Use when direct and indirect authorship leaks must be removed with applied PDF redactions while preserving pages, scientific content, and bibliography.
---

# Blind PDF anonymization

This Skill creates real PDF redaction annotations from exact searchable text and applies them, removing underlying text rather than drawing visual overlays. It preserves the source page count and does not use area-based deletion.

It requires Python and PyMuPDF (`fitz`) in the execution environment and has no network dependency.

## Current task: required deliverables

Create all three files before completion:

- `/root/redacted/paper1.pdf` from `/root/paper1.pdf`
- `/root/redacted/paper2.pdf` from `/root/paper2.pdf`
- `/root/redacted/paper3.pdf` from `/root/paper3.pdf`

The task entrypoint creates `/root/redacted` itself. Run it from the package directory against pristine source PDFs:

```sh
python scripts/anonymize_task.py <<'JSON' > /root/anonymization-report.json
{}
JSON
```

Do not use an already-redacted output as a source. The command emits JSON validation reports and exits nonzero without replacing a destination when a document fails validation.

## Method

1. **Discover before redacting.** Use the task entrypoint's conservative automatic discovery, then inspect the sources with `scripts/discover.py`. Read every title/byline, author note, header/footer, contribution statement, acknowledgement, and text before References. Look for full author names, affiliations, emails, correspondence information, acknowledgement names, the submission's own arXiv/DOI, and acceptance or venue statements. Inspect PDF metadata too.
2. **Use exact reviewed targets for anything automatic discovery missed.** Names embedded in acknowledgement prose and unusual author/contribution formats require human review. Never redact only a surname and never redact an entire acknowledgement section or a broad page region.
3. **Protect the bibliography.** References and self-citations remain intact. Own-paper identifiers are redacted before References; if an identifier repeats in a running header on a References page, restrict that target to its header/footer match using `regions`.
4. **Verify outputs.** The program reopens each output, confirms page-count preservation, checks that selected text is no longer extractable, clears identity-bearing metadata, and rejects excessive non-target text loss. Inspect the report and open the resulting PDFs to ensure abstract, body, figures, tables, equations, and references remain readable.

## Adding reviewed targets

Re-run `scripts/anonymize_task.py` from original inputs with optional target lists keyed by source filename:

```json
{
  "auto_discover": true,
  "targets": {
    "paper1.pdf": [
      {"text": "exact reviewed acknowledgement name", "scope": "before_references"}
    ],
    "paper2.pdf": [],
    "paper3.pdf": []
  }
}
```

A target has these fields:

- `text` — required nonempty exact source string.
- `scope` — `before_references` (default), `pages`, or `all`.
- `pages` — required one-based page numbers for `scope: "pages"`; may additionally narrow another scope.
- `regions` — optional `[{"page": 1, "rect": [x0, y0, x1, y1]}]`. Regions only filter `page.search_for(text)` hits; no supplied rectangle is redacted by itself.
- `required` — defaults to `true`; a required target without an eligible match is an error.

Use `before_references` for ordinary title-page and body identity leaks. Use `all` only when every occurrence is identifying. For a header/footer occurrence that must be removed while an identical bibliography occurrence must remain, use `scope: "all"` with narrow match-filtering `regions`.

## Script interfaces

All scripts accept one JSON object on stdin and emit JSON on stdout. Invalid schema, missing files, unreadable PDFs, unavailable PyMuPDF, unmatched required targets, page-count changes, selected text remaining, metadata failures, or destructive text loss cause JSON on stderr and a nonzero exit.

- `scripts/discover.py`
  - Input: `{"inputs":["source.pdf", ...]}`
  - Output: per-page extracted text, metadata, References boundary, and candidate direct identifiers for review.
- `scripts/anonymize.py`
  - Input: `{"documents":[{"input":"source.pdf","output":"redacted.pdf","auto_discover":true,"clear_metadata":true,"targets":[target]}]}`
  - Output: `{"documents":[report],"valid":true}`.
- `scripts/anonymize_task.py`
  - Input: `{}` or `{"auto_discover":true,"targets":{"paper1.pdf":[target]}}`
  - Output: reports after writing exactly the three required `/root/redacted/paper{1-3}.pdf` files.
