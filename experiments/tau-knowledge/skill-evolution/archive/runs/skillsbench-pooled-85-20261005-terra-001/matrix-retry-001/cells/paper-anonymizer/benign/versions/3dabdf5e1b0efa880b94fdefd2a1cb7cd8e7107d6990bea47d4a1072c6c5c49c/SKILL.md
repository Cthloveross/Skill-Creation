---
name: blind-pdf-anonymizer
description: Produce same-page-count, truly redacted PDF copies of academic papers for blind review. Use for supplied PDFs that need author, affiliation, contact, acknowledgement, publication-identifier, and metadata anonymization while preserving the scientific text and bibliography.
---

# Blind PDF anonymization

Create the required artifacts immediately with the packaged entrypoint. It reads every supplied PDF, applies real PyMuPDF redactions, and writes the requested filenames; a prose description is not a deliverable.

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

For this task, successful delivery requires these exact paths:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

The entrypoint creates `output_dir`, preserves each input basename, leaves input files unchanged, and emits an audit JSON document on stdout. Confirm every job reports `readable: true`, `page_count_matches: true`, and its expected output path before concluding.

## Method

The script extracts all pages before making changes and finds the References/Bibliography boundary. Before that boundary it discovers exact, concrete text targets from the title matter and acknowledgement prose, including byline-like full names, affiliation lines, email addresses, arXiv identifiers, DOIs, and acceptance/publication wording. It also uses any Author metadata value as an additional candidate and clears document/XMP identifying metadata.

Every content removal is derived from `page.search_for(exact_text)`, then applied with `add_redact_annot` and `apply_redactions`. It does not mask guessed page regions or draw visual-only overlays. Automatic removal is limited to pre-reference content, including only the part above a References heading when it shares a page with the paper body. Bibliography entries and self-citations are retained.

After initial output, inspect the audit's unmatched targets and review extracted text, page headers/footers, title blocks, footnotes, and acknowledgement sentences. If a concrete identity string was missed, rerun with reviewed full-string targets. Do not supply surname-only targets or cited-paper identifiers that occur solely in References.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Full reviewed acknowledgement name", "scope": "before_references"},
      {"text": "Recurring identity leak in a header", "scope": "all"},
      {"text": "Known leak on selected pages", "scope": "pages", "pages": [0, 3]}
    ]
  }
}
```

## Script JSON interface

`scripts/anonymize_batch.py` reads one JSON object from stdin and writes one JSON object to stdout.

- `inputs` — required nonempty array of existing PDF paths.
- `output_dir` — required output directory; output names equal source basenames.
- `targets_by_input` — optional map from input path to reviewed target objects.
- `report_path` — optional audit JSON path.

A target has nonempty `text` and `scope` of `before_references` (default), `all`, or `pages`; `pages` requires a nonempty zero-based page-number list. Invalid input, unreadable PDFs, or an output whose page count changes cause a JSON error and nonzero exit. The audit records every searched target, its exact-match redaction count, and any unmatched manual targets.
