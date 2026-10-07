---
name: blind-review-pdf-anonymizer
description: Produce page-preserving, truly redacted blind-review PDFs from supplied academic papers. Use when names, affiliations, emails, acknowledgements, author-identifying headers, preprint/publication identifiers, and PDF metadata must be removed without damaging scientific content or bibliography.
---

# Blind-review PDF anonymizer

This Skill must produce the requested PDF artifacts, not merely inspect papers or provide a redaction plan. For the current task, run this exact batch operation from the Skill package directory before giving the user a final response:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

The required deliverables created by that operation are exactly:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

Do not stop after source-text discovery. A successful task requires all three files to exist at those exact paths.

## Method

The entrypoint uses PyMuPDF to copy and redact the existing PDFs rather than reconstructing them. It reads every source page first, detects the References/Bibliography boundary, discovers concrete identity candidates in the title block and pre-reference content, adds redaction annotations only around `page.search_for()` results, applies those annotations, and saves a new PDF with the original basename.

Automatic candidates include title-block author-like names and affiliation lines, emails, arXiv IDs, DOI strings, acknowledgement names following common acknowledgement constructions, author-contribution/correspondence lines, and short accepted/published venue statements. Searches are restricted to content before References so bibliography entries and self-citations remain intact. Metadata, including Author and XMP metadata, is cleared separately.

A paper can contain unusual acknowledgement names or PDF encodings that require a reviewed exact string. First run the standard batch operation so that required artifacts are created. If the audit or visual/text review identifies a real unredacted identity leak, rerun using only exact strings found in that source, for example:

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact acknowledgement person name", "scope": "before_references"},
      {"text": "Exact repeated header", "scope": "all"},
      {"text": "Exact known leak", "scope": "pages", "pages": [0, 2]}
    ]
  }
}
```

Never use a broad page rectangle, redact an isolated surname, or redact an identifier solely because it appears in the reference list. Such actions destroy scientific content or citations. Use an exact full string and the narrowest appropriate scope.

## Validation and completion

The script emits one JSON object on stdout and optionally writes the same audit to `report_path`. It returns `status: "ok"` only after each output was reopened successfully and confirmed to have the original page count. Confirm every job reports `readable: true` and `page_count_matches: true`, and verify the three required output paths exist.

The audit lists unmatched candidates and residual text matches. A manually supplied target with a source match must not occur in the extracted output. Preserve the abstract, body, figures, equations, tables, captions, and references; only concrete identity-bearing strings should disappear.

## JSON interface

`scripts/anonymize_batch.py` reads a JSON object from stdin and writes a JSON object to stdout.

- `inputs`: required nonempty array of existing PDF path strings.
- `output_dir`: required output directory. Each output name is its source basename.
- `targets_by_input`: optional object mapping an exact input path to reviewed target objects.
- `report_path`: optional audit JSON destination.
- Each target has nonempty `text`; optional `scope` is `before_references` (default), `all`, or `pages`. A `pages` target requires a nonempty zero-based `pages` array.

Invalid input, unavailable PyMuPDF, unreadable PDFs, or a changed page count causes an error JSON response and nonzero exit. Inputs are never overwritten.
