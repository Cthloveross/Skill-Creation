---
name: blind-review-pdf-anonymizer
description: Produce page-preserving, truly redacted PDFs for blind academic review. Use when supplied papers must have author identities, affiliations, contact details, acknowledgements, preprint/publication leaks, running identifiers, and PDF metadata removed without deleting scientific content or bibliographies.
---

# Blind-review PDF anonymizer

This Skill creates deliverable PDFs; do not stop after inspecting the papers or writing an audit. The supplied files must be processed and saved before the task is complete.

For the current task, run the entrypoint from this package directory as the first artifact-producing action:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

The required outputs are exactly:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

## Method

The entrypoint opens and modifies the existing PDFs with PyMuPDF. It extracts all pages, determines the References/Bibliography boundary, discovers exact candidate identity strings outside the bibliography, adds search-based redaction annotations, applies them, clears document/XMP metadata, and atomically writes an output using the source basename. It never reconstructs pages, deletes pages, or uses a broad title/acknowledgement/page rectangle.

Automatic candidates include title-block personal names and affiliation lines, emails, arXiv IDs, DOIs, acknowledgement names following common acknowledgement wording, correspondence/contribution disclosures, and acceptance/publication/venue disclosure lines. A target is searched on every applicable page before References so repeated headers and footers are covered. References and self-citations are excluded from automatic redaction.

After the initial artifact-producing run, inspect the audit and source text, especially for unusual acknowledgement wording, name spellings, title-block variants, headers, footers, and own publication disclosures. If a concrete leak was missed, rerun with it as an exact reviewed target. Do not redact an isolated surname, an entire section, a page region, or bibliography text.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact person name", "scope": "before_references"},
      {"text": "Exact running header", "scope": "pages", "pages": [0, 2]},
      {"text": "Exact own-publication disclosure", "scope": "before_references"}
    ]
  }
}
```

Use `scope: "all"` only for an exact reviewed identifier that is demonstrably identity-revealing wherever it appears; it may affect references and is therefore normally inappropriate. `pages` uses zero-based page numbers.

## Entrypoint JSON interface

`scripts/anonymize_batch.py` reads one JSON object from stdin and emits one JSON object on stdout.

- `inputs`: required nonempty array of existing PDF paths.
- `output_dir`: required destination directory. Outputs use each input basename.
- `targets_by_input`: optional mapping from an input path to reviewed target objects.
- `report_path`: optional path for the same JSON audit emitted on stdout.
- Each target has nonempty `text`, optional `scope` (`before_references`, `pages`, or `all`), and a nonempty `pages` array for `pages` scope.

The result records saved path, source/output page counts, targets and hit counts, unmatched manual targets, residual matched targets, and metadata cleanup. An input error is reported per job while remaining inputs are attempted. Treat any job error, `unmatched_manual_targets`, or `residual_targets_before_references` as requiring correction.

## Validation

Run the optional validator after production:

```bash
python scripts/verify_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted"}
JSON
```

It checks existence, PDF readability, exact page-count preservation, nontrivial text, blank/anonymized Author metadata, and that explicitly supplied reviewed targets no longer occur. It does not replace a human review of identity-bearing prose. Completion requires all requested output PDFs to exist and open successfully with their original page counts.
