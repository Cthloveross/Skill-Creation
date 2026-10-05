---
name: blind-review-pdf-anonymizer
description: Produce page-preserving, truly redacted PDFs for blind academic review. Use for supplied PDFs that must have author identities, affiliations, contact details, acknowledgement names, publication/preprint leaks, running identifiers, and identifying metadata removed without altering scientific content or bibliography.
---

# Blind-review PDF anonymizer

This Skill must produce artifacts, not merely an audit or instructions. First run the packaged entrypoint against the supplied PDFs. For the requested batch, execute it with this JSON on stdin:

```json
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
```

Use `scripts/anonymize_batch.py`. It creates the output directory and writes each result using the source basename. Completion requires these exact files:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

Then run `scripts/verify_batch.py` with the same `inputs` and `output_dir`. Do not finish if a required output is absent, unreadable, or has a different page count.

## Method

The anonymizer modifies the existing PDF with PyMuPDF search-based redaction annotations and applies those annotations, removing underlying text rather than drawing an overlay or rebuilding pages. It scans all pages before the References/Bibliography heading for exact candidates including title-block names and affiliations, email addresses, arXiv IDs, DOIs, acknowledgement names, correspondence/contribution notes, and publication/venue disclosures. It removes identifying document metadata and XMP. References are excluded from automatic redaction so bibliography entries and self-citations survive.

Review `/root/redacted/anonymization-audit.json` and the source text before declaring completion. If a concrete unusual leak is visible, particularly a name in free-form acknowledgement prose, rerun using `targets_by_input` with reviewed full strings. Never redact only a surname, an arbitrary page region, or a whole acknowledgement section.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Reviewed full person name", "scope": "before_references"},
      {"text": "Reviewed running identifier", "scope": "pages", "pages": [0, 1]},
      {"text": "Reviewed own-publication disclosure", "scope": "before_references"}
    ]
  }
}
```

`scope` is `before_references` (default), `pages` (with zero-based `pages`), or `all`. Use `all` only for a reviewed identity string that is sensitive everywhere; it can otherwise damage bibliography content.

## Entrypoint interface

`scripts/anonymize_batch.py` reads one JSON object from stdin and emits one JSON result on stdout.

- `inputs`: required nonempty array of existing PDF paths.
- `output_dir`: required destination directory.
- `targets_by_input`: optional input-path map to reviewed target objects.
- `report_path`: optional audit JSON path.

The report records matching rectangles, unmatched reviewed targets, residual targets, metadata cleanup, and original/output page counts. A residual or unmatched reviewed target requires review and correction. `scripts/verify_batch.py` accepts `{"inputs":[...],"output_dir":"/..."}` and reports existence, readability, page-count equality, meaningful extracted text, and Author metadata status.
