---
name: blind-pdf-anonymizer
summary: Produce same-page-count, true-redacted PDFs for blind review from supplied PDFs.
description: Use for academic PDFs that must be anonymized without deleting scientific content or bibliography entries. The primary entrypoint creates the requested output PDFs, uses exact search-derived redactions, clears identity-bearing metadata, and emits an audit suitable for manual review.
---

# Blind PDF anonymization

Use the runnable batch entrypoint first. It is deliberately an **in-place PDF redaction** workflow: it retains the original pages, figures, equations, and references rather than rebuilding the paper from extracted text.

```bash
python scripts/anonymize_batch.py <<'JSON'
{
  "inputs": ["/root/paper1.pdf", "/root/paper2.pdf", "/root/paper3.pdf"],
  "output_dir": "/root/redacted",
  "report_path": "/root/redacted/anonymization-audit.json"
}
JSON
```

For the current task this command must create exactly:

* `/root/redacted/paper1.pdf`
* `/root/redacted/paper2.pdf`
* `/root/redacted/paper3.pdf`

## What the entrypoint does

For each runtime-supplied input it extracts page text, determines the References/Bibliography boundary, and creates an explicit audit list of exact strings found in:

* title-block author-like strings and affiliation lines;
* emails, arXiv IDs (including legacy IDs), and DOIs before References;
* acknowledgement names in standard acknowledgement constructions;
* correspondence/contribution notes and explicit accepted/published-venue lines; and
* supplied manual targets.

Every applied mark is created only from `page.search_for(exact_string)` rectangles followed by `add_redact_annot()` and `apply_redactions()`. It never uses guessed page areas, raster overlays, or PDF reconstruction. Searches are limited to pre-References content (and to the portion before a References heading when that heading shares a page), unless a reviewed target explicitly has another scope. It clears Author, Creator, Subject, and Keywords document metadata and clears XMP metadata.

The JSON stdout and optional audit file report the inferred References page, every candidate, the number of rectangles actually redacted, unmatched candidates, page counts, and metadata actions. A readable output is written even if there are no automatically recognized strings, so artifact production does not depend on a candidate being present.

## Review and add exact targets when necessary

Read the audit and inspect each source/output PDF, particularly the title block, running headers/footers, acknowledgements, contribution notes, and pages immediately before References. Automatic recognition is a discovery aid, not a substitute for reading free-form acknowledgement prose or unusual PDF typography.

If review identifies a missed exact string, rerun with `targets_by_input`. Keys are the same input path strings passed in `inputs`; values are target objects. Each object has `text`, plus one scope:

* `before_references` (default): all content before the bibliography boundary;
* `pages`: a reviewed list of zero-based page indexes; or
* `all`: all pages, only for a paper-owned repeated identifier whose every occurrence should disappear.

For example, with placeholders rather than task values:

```json
{
  "inputs": ["/path/a.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/a.pdf": [
      {"text": "Exact acknowledged person", "scope": "before_references"},
      {"text": "paper-owned identifier", "scope": "pages", "pages": [0, 7]}
    ]
  }
}
```

Use full discovered names rather than isolated surnames. Preserve self-citations, author names, arXiv IDs, and DOIs **inside bibliography entries**. Do not blank an acknowledgement section: add only the named people or other concrete identifying strings it contains. A scan/image-only identity leak cannot be safely removed with a broad rectangle; OCR or a reviewed text-capable source is required.

## Validation

Before delivery, confirm in the audit that every output is `readable`, `page_count_matches` is true, and there are no unexpected unmatched manual targets. Reopen the PDFs and extract/search their text to confirm all reviewed targets are absent from their intended scopes. Compare source and output text: differences should be limited to the audited targets and metadata; references and scientific body text must remain substantially unchanged.

### Entrypoint JSON interface

`anonymize_batch.py` reads one JSON object on stdin and emits one JSON object on stdout.

Required fields:

* `inputs`: nonempty array of existing PDF path strings.
* `output_dir`: destination directory. Output filenames are the input basenames.

Optional fields:

* `targets_by_input`: object mapping an input path to explicit target arrays as described above.
* `report_path`: UTF-8 JSON audit destination.

It exits nonzero and emits `{ "status": "error", ... }` for malformed input or an unreadable input PDF. It creates parent directories and never modifies source PDFs.
