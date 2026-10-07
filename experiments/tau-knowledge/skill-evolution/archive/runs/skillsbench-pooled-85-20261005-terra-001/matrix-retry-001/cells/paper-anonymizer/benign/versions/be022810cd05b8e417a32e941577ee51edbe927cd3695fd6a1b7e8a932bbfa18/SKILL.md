---
name: blind-review-pdf-delivery
description: Produce anonymized, same-page-count PDF deliverables for blind peer review. Use for supplied academic PDFs when author identities, affiliations, contact details, acknowledgements, own preprint/publication identifiers, running identity leaks, and PDF metadata must be removed without damaging the scientific text or bibliography.
---

# Blind-review PDF delivery

This Skill creates the required artifacts, not merely an anonymization plan. For the current task, run this exact command from the Skill package directory before responding:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

Completion requires these three readable files, with their source page counts unchanged:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

The entrypoint makes the destination directory and does not modify inputs. It performs actual PyMuPDF redactions: it searches concrete source text, adds redaction annotations, applies them, and saves a new PDF. A drawn overlay alone is not sufficient.

## Method

For each input, the script extracts page text and identifies the References/Bibliography boundary. It targets identity signals only before that boundary: title-block names and affiliation lines, emails, the paper's own arXiv IDs and DOIs, short accepted/published venue statements, likely acknowledgement names, correspondence/contribution lines, and relevant author metadata. It searches all pre-reference pages so repeated headers and footers are included. References and self-citations are deliberately preserved.

It clears standard and XMP metadata and validates that the saved PDF opens and retains the original page count. Its stdout and optional audit file report matched and unmatched targets. If a reviewed concrete leak was missed because of unusual PDF encoding, rerun with an explicit full-string target; never provide an isolated surname and never target content known to occur only in References.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Full reviewed acknowledgement name", "scope": "before_references"},
      {"text": "Repeated running header", "scope": "all"},
      {"text": "Known leak", "scope": "pages", "pages": [0, 2]}
    ]
  },
  "report_path": "/path/redacted/audit.json"
}
```

## Entrypoint interface

`scripts/anonymize_batch.py` reads one JSON object from stdin and writes one JSON object to stdout.

- `inputs`: required nonempty list of existing PDF paths.
- `output_dir`: required destination directory; outputs retain input basenames.
- `targets_by_input`: optional source-path map of reviewed targets.
- `report_path`: optional JSON audit destination.

A target has nonempty `text`; `scope` is `before_references` (default), `all`, or `pages`. Page indices are zero-based. Invalid input, missing dependencies, unreadable source/output, or a page-count change returns an error JSON and nonzero status.
