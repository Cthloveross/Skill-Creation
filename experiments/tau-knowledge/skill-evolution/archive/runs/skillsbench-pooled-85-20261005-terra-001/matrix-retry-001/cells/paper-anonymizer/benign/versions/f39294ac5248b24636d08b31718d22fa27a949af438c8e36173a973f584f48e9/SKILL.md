---
name: blind-review-pdf-anonymizer
description: Create deliverable blind-review versions of supplied academic PDFs. Use when PDF author names, affiliations, emails, acknowledgements, publication/preprint identifiers, running headers, and metadata must be irreversibly redacted while preserving page count, scientific content, and bibliography.
---

# Blind-review PDF anonymizer

This Skill produces PDF artifacts; it is not just a review checklist. For the current task, the executor must run the following single batch action before responding to the user:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

This creates the required files exactly at:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

Do not stop after inspecting the source PDFs or printing a plan. The output PDFs are the required deliverables.

## What the entrypoint does

The script opens each source in place with PyMuPDF, never modifies the input, and saves an independently readable PDF with the same basename in `output_dir`. It discovers concrete candidates from source text before making any change, including title-block names and affiliations, email addresses, pre-reference arXiv and DOI strings, acceptance/publication statements, acknowledgement names, correspondence/contribution notes, and author metadata. It searches every eligible page for each concrete string, adds actual redaction annotations, and applies them. Thus removed text is not recoverable through normal PDF text extraction; it is not merely covered by a drawn rectangle.

References and self-citations are preserved. Automatic identity targets are restricted to material before the References/Bibliography boundary (including the body portion of a page that begins References). Metadata and XMP metadata are cleared independently.

## Required validation

Read the JSON emitted by the script. `status` must be `ok`; each job must report `readable: true` and `page_count_matches: true`. Confirm the three output paths exist. If the audit reports an unmatched target discovered through human inspection, use the target's exact extracted source string in a rerun rather than using a broad region or an isolated surname.

The script also supports explicit reviewed targets for cases such as unusual text encoding or names in free-form acknowledgement prose. Add only strings actually found in the supplied source. Never provide a target that occurs only in the reference list.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact reviewed acknowledgement name", "scope": "before_references"},
      {"text": "Exact repeated running header", "scope": "all"},
      {"text": "Exact known leak", "scope": "pages", "pages": [0, 3]}
    ]
  },
  "report_path": "/path/redacted/audit.json"
}
```

## Script JSON interface

`scripts/anonymize_batch.py` receives one JSON object on stdin and writes one JSON result object on stdout.

- `inputs` is a required nonempty list of existing PDF paths.
- `output_dir` is a required destination directory. Output names equal source basenames.
- `targets_by_input` is an optional mapping from each exact input path to reviewed target objects.
- `report_path` is an optional audit JSON path.
- A target has nonempty `text` and `scope` of `before_references` (default), `all`, or `pages`; `pages` uses zero-based page numbers and is required for `pages` scope.

Invalid requests, unreadable PDFs, unavailable PyMuPDF, or a changed page count return `{"status":"error",...}` and a nonzero exit status. The script should be rerun only with a corrected input or more precise reviewed targets; do not substitute visual overlays or page-area masking.
