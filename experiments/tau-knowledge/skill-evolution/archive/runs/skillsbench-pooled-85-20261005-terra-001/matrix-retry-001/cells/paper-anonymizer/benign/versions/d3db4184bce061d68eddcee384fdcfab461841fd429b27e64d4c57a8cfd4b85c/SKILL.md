---
name: blind-review-pdf-anonymizer
description: Create deliverable, page-preserving anonymized PDFs for blind review from supplied academic PDFs. Use when author names, affiliations, contact details, acknowledgements, publication/preprint leaks, running identifiers, and document metadata must be removed while retaining the scientific paper and bibliography.
---

# Blind-review PDF anonymizer

This is an artifact-producing Skill. Do not only describe a workflow, inspect files without saving them, or return before the PDFs exist. Use the terminal to run this command from the package directory immediately:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

The required completion artifacts are exactly:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

The entrypoint modifies existing PDFs with PyMuPDF true redactions; it does not recreate pages or make visual-only overlays. It creates `/root/redacted` itself, uses the source basename for every output, preserves pages, removes identifying metadata/XMP, and reopens every saved PDF before reporting success.

## Required review and scope

The script automatically discovers conservative, exact identity candidates outside References: title-block names and affiliation lines, emails, arXiv IDs, DOIs, acknowledgement names in common acknowledgement wording, correspondence/contribution lines, and accepted/publication/venue disclosures. It searches all eligible pages, so recurring headers and footers are included. The bibliography is protected: automatic candidates never redact text at or below a References/Bibliography heading, so self-citations and cited-paper identifiers remain.

After the production command, inspect the audit and source/output text. If an unusual concrete identity leak remains (especially a person name in acknowledgement prose), rerun the same command with reviewed exact targets. Do not redact a surname alone, a whole section, or an arbitrary page region.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact reviewed person name", "scope": "before_references"},
      {"text": "Exact recurring header", "scope": "pages", "pages": [0, 2]},
      {"text": "Exact own-publication statement", "scope": "before_references"}
    ]
  }
}
```

`scope` is `before_references` (default), `pages`, or `all`; `pages` is a nonempty zero-based list. `all` must only be used for a reviewed identifier that is sensitive everywhere, because it can affect bibliography text.

## JSON entrypoint interface

`scripts/anonymize_batch.py` receives one JSON object on stdin and emits one JSON object on stdout.

- `inputs`: required, nonempty array of existing PDF paths.
- `output_dir`: required output directory.
- `targets_by_input`: optional map of input path to reviewed target objects.
- `report_path`: optional audit destination.

The report records output paths, page counts, every target and matching rectangle count, unhandled manual targets, residual target strings, and metadata cleanup. A result whose `status` is not `ok`, that has an absent output, page-count mismatch, unmatched manual target, or residual target requires correction before completion.

Validate saved deliverables after production:

```bash
python scripts/verify_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted"}
JSON
```

Completion requires all three required paths to be readable PDFs with the original page count. The validator is structural; review acknowledgement prose and any unusual author-linked wording as well.
