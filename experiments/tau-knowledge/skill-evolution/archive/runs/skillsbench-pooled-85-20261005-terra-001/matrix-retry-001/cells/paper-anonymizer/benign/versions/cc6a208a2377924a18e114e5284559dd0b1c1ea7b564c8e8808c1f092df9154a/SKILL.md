---
name: blind-review-pdf-anonymizer
description: Produce page-preserving, true-redacted PDFs for blind peer review from supplied academic PDFs. Use when author names, affiliations, emails, acknowledgements, headers, preprint/publication identifiers, and PDF metadata must be anonymized without removing scientific content or bibliographic references.
---

# Blind-review PDF anonymizer

This Skill produces required artifacts. Do not merely report a plan, list leaks, or leave an audit file: execute the entrypoint and ensure the requested PDFs exist before finishing.

For the current task, run this from the package directory:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

The mandatory deliverables are exactly:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

## Method

The entrypoint opens and modifies the existing PDFs with PyMuPDF. It first extracts all text and identifies concrete candidate authorship leaks before the References/Bibliography boundary. It then uses `page.search_for`, redaction annotations, and `apply_redactions` to remove matched text data rather than drawing visual overlays. It processes every relevant page, keeps the original page count, and sanitizes PDF/XMP metadata.

Automatic targets include title-block author-like strings and affiliations, email addresses, arXiv IDs, DOIs, acknowledgement names following thank-you language, acceptance/publication lines, correspondence/contribution notes, and repeated header/footer leaks that match discovered direct identifiers. The bibliography is never in automatic redaction scope. Self-citations and identifiers belonging to cited works are retained.

If review of the audit exposes an unusual concrete leak that was not detected, rerun only the affected source with a narrow reviewed target. Do not use isolated surnames or broad regions.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact person name in acknowledgement", "scope": "before_references"},
      {"text": "Exact running header identifier", "scope": "pages", "pages": [0, 2]}
    ]
  }
}
```

## Completion checks

The script writes a JSON audit to stdout and optionally to `report_path`. It reopens every output and checks page-count preservation. Before completion, confirm each requested output exists, is readable, and reports `page_count_matches: true`. Inspect `unmatched_manual_targets` and `residual_targets_before_references`; do not silently accept an unmatched reviewed leak.

Never delete pages, reconstruct PDFs from extracted text, redact an entire area/page, or redact citation entries merely because they contain names, arXiv IDs, or DOIs.

## JSON interface

`scripts/anonymize_batch.py` reads one JSON object on stdin and emits one JSON object on stdout.

- `inputs` required: nonempty array of existing PDF path strings.
- `output_dir` required: destination directory; each output retains its input basename.
- `targets_by_input` optional: map from an exact input path to reviewed target objects.
- `report_path` optional: audit JSON output path.
- Target fields: nonempty `text`; `scope` of `before_references` (default), `all`, or `pages`; `pages` is a nonempty zero-based page array when that scope is selected.

Bad JSON, absent input, unavailable PyMuPDF, invalid target scope/page, unreadable output, or a changed page count returns an error JSON object and a nonzero status. Inputs are never overwritten.
