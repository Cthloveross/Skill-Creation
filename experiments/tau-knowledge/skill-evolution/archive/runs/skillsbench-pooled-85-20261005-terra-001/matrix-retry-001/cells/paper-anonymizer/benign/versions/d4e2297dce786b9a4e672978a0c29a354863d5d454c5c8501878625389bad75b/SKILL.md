---
name: blind-pdf-anonymizer
summary: Produce true-redacted, same-page-count academic PDFs for blind review.
description: Use for supplied academic PDF papers that require removal of author identities and paper-owned identifiers while retaining scientific content, layout, and bibliography.
---

# Blind PDF anonymization

This is an artifact-producing task: run the entrypoint before responding. It creates the requested PDFs; reading or describing the script does not create them.

```bash
python scripts/anonymize_batch.py <<'JSON'
{
  "inputs": ["/root/paper1.pdf", "/root/paper2.pdf", "/root/paper3.pdf"],
  "output_dir": "/root/redacted",
  "report_path": "/root/redacted/anonymization-audit.json"
}
JSON
```

For the supplied task, verify that these exact deliverables exist after the command completes:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

## Method

The entrypoint opens and modifies the original PDFs with PyMuPDF rather than reconstructing them. It extracts every page, determines the References/Bibliography boundary, and builds concrete targets from title-block author-like strings and affiliations, email addresses, paper-owned pre-reference arXiv IDs and DOIs, acknowledgement-context names, correspondence/contribution notes, and acceptance/publication statements. It clears identifying document and XMP metadata.

Every removal is a real PDF redaction: the script obtains an exact `page.search_for()` match, adds a redaction annotation, then applies annotations. It never masks a guessed page region or draws a merely visual overlay. The default search area ends at References, including only the material above a References heading that shares a page. Thus normal bibliography entries and self-citations remain intact.

Review the JSON audit, especially `unmatched_manual_targets` and `unmatched_automatic_candidates`. Inspect title pages, repeated headers/footers, footnotes, and acknowledgement prose. If a reviewed leak was missed, rerun using the optional `targets_by_input` field with a full exact string; do not use a surname alone. Use `scope: "all"` only for a confirmed paper-owned repeated leak. Do not target identifiers that occur only in bibliographic citations.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact reviewed acknowledgement name", "scope": "before_references"},
      {"text": "Reviewed recurring identifier", "scope": "pages", "pages": [0, 3]},
      {"text": "Confirmed all-page paper-owned leak", "scope": "all"}
    ]
  }
}
```

## JSON interface and delivery validation

`scripts/anonymize_batch.py` reads one JSON object on stdin and writes one JSON audit object to stdout.

- `inputs` is a nonempty array of existing PDF paths.
- `output_dir` is required. Outputs retain each source basename.
- `targets_by_input` is optional and maps input paths to arrays of target objects.
- `report_path` is optional and writes the same audit to UTF-8 JSON.

Each manual target needs nonempty `text`. Its `scope` is `before_references` (default), `pages` with zero-based `pages`, or `all`. The script creates required output directories, does not alter sources, and returns JSON error status on invalid input or unreadable PDFs.

Before delivery, confirm every job reports `readable: true` and `page_count_matches: true`; reopen each output if necessary. Confirm reviewed target strings do not extract from output text. Compare source and output text to ensure removals are limited to audited identity material and that scientific prose, figures, equations, and bibliography remain substantially unchanged.
