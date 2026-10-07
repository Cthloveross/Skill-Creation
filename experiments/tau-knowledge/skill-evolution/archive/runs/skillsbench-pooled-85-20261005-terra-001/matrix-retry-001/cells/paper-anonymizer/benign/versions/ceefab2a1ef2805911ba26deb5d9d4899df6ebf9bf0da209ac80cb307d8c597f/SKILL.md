---
name: blind-review-pdf-anonymizer
description: Create page-preserving, truly redacted PDFs for blind peer review from supplied academic PDFs. Use when author names, affiliations, emails, acknowledgements, author-identifying headers, preprint/publication identifiers, and identifying PDF metadata must be removed while preserving scientific content and references.
---

# Blind-review PDF anonymizer

This is an artifact-producing Skill. Do not stop after inspecting the PDFs or describing a redaction plan: run the batch entrypoint and leave the required PDFs on disk.

For the current task, from the Skill package directory, run:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

The mandatory deliverables are exactly:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

Do not rename them, save them elsewhere, delete pages, or replace the PDFs with extracted/reconstructed text.

## Procedure

The entrypoint reads each supplied PDF, discovers concrete candidate leaks before its References/Bibliography boundary, applies PyMuPDF redaction annotations to exact `page.search_for()` matches, applies the annotations, clears identifying PDF/XMP metadata, and saves the edited existing document under the source basename. It processes all pages before References, so repeated title-page and running-page leaks can be removed without touching bibliography entries.

Automatic discovery covers:

- author-like title-block names and affiliation lines;
- emails, arXiv identifiers, and DOI strings before References;
- names in acknowledgement prose following common thank-you constructions;
- correspondence/contribution notes and short accepted/published venue lines;
- identifying document metadata.

References and self-citations must remain intact. Do not redact a source identifier merely because it appears in a cited reference. Never use broad area/page redactions or visual overlays: only exact text-search rectangles are valid redactions.

If review of the audit or PDF identifies a concrete, unusual leak which automatic discovery missed, rerun for that source with an explicit exact target. The text must be copied from the source PDF and scoped as narrowly as possible:

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact acknowledgement person name", "scope": "before_references"},
      {"text": "Exact repeated header leak", "scope": "pages", "pages": [0, 2]}
    ]
  }
}
```

Do not supply isolated surnames, generic institution words, or broad text regions as targets.

## Completion checks

The script emits JSON and, when requested, writes the same audit JSON to `report_path`. It exits successfully only after reopening every output and checking the original page count. Before completing the task, confirm:

1. all three mandatory paths exist and each is a readable PDF;
2. every job reports `page_count_matches: true` and `readable: true`;
3. `residual_matched_targets` is empty;
4. any unmatched automatic/manual candidate is inspected rather than ignored; and
5. the body, figures, equations, tables, captions, and bibliography remain present.

## JSON interface

`scripts/anonymize_batch.py` reads one JSON object from stdin and writes one JSON object to stdout.

- `inputs` (required): nonempty array of existing PDF path strings.
- `output_dir` (required): directory in which each source basename is written.
- `targets_by_input` (optional): map from an exact input path to an array of reviewed target objects.
- `report_path` (optional): path where the JSON audit is written.
- A target requires nonempty `text`; `scope` is `before_references` (default), `all`, or `pages`. `pages` requires a nonempty zero-based page-number array.

Bad JSON, missing input, unavailable PyMuPDF, invalid target scope, unreadable output, or changed page count produces an error JSON response and nonzero exit status. Input PDFs are never overwritten.
