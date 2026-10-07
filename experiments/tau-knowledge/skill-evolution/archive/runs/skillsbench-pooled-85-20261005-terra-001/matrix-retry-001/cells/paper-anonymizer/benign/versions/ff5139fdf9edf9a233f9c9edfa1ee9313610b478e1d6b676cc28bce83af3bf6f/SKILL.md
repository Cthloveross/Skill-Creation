---
name: blind-pdf-anonymizer
summary: Create true-redacted, same-page-count academic PDFs for blind review.
description: Use this Skill to generate anonymized copies of supplied academic PDFs, removing authorship signals and paper-owned identifiers while preserving scientific content and bibliography.
---

# Blind PDF anonymization

This task is incomplete until the output files are written. **Run the entrypoint below before giving a final response.** It creates the requested deliverables directly; describing the procedure does not create PDFs.

```bash
python scripts/anonymize_batch.py <<'JSON'
{
  "inputs": ["/root/paper1.pdf", "/root/paper2.pdf", "/root/paper3.pdf"],
  "output_dir": "/root/redacted",
  "report_path": "/root/redacted/anonymization-audit.json"
}
JSON
```

For the supplied papers, delivery requires all of these exact paths:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

## What the entrypoint does

The script edits each source PDF in place with PyMuPDF and preserves its page count. It reads every page before redacting, identifies the References/Bibliography boundary, and creates exact search targets for:

- title-block byline-like names and affiliation lines;
- email addresses;
- paper-owned pre-reference arXiv IDs and DOIs;
- acknowledgement names following common acknowledgement wording;
- acceptance/publication statements; and
- identifying standard and XMP PDF metadata.

Each removal uses `page.search_for()` followed by a redaction annotation and `apply_redactions()`. It never covers a guessed rectangular page region or makes a visual-only overlay. Automatic text targets are restricted to content before References, including only the portion before a References heading on a shared page. Bibliography entries and self-citations remain unchanged.

The script emits an audit JSON object. Confirm every job has `readable: true`, `page_count_matches: true`, and an output at the required path. Inspect `unmatched_manual_targets` if manual targets were supplied. The generated audit is not a required deliverable, but is useful for review.

## Optional reviewed targets

After inspecting extracted text, headers/footers, footnotes, and acknowledgement prose, rerun with `targets_by_input` for any concrete missed identity string. Use full reviewed names rather than surnames. Do not target cited-paper identifiers or author names occurring solely in References.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact reviewed acknowledgement name", "scope": "before_references"},
      {"text": "Confirmed recurring paper-owned leak", "scope": "all"},
      {"text": "Known page-specific leak", "scope": "pages", "pages": [0, 2]}
    ]
  }
}
```

## JSON interface

`scripts/anonymize_batch.py` reads one JSON object from stdin and writes one JSON object to stdout.

- `inputs`: required nonempty array of existing PDF paths.
- `output_dir`: required destination directory. Each output retains the input basename.
- `targets_by_input`: optional map from input path to target arrays.
- `report_path`: optional JSON audit output path.

A manual target has nonempty `text` and a `scope`: `before_references` (default), `all`, or `pages` with a nonempty zero-based `pages` array. Invalid requests and unreadable PDFs yield a JSON error and nonzero exit status. The script creates output directories, leaves sources unchanged, clears identifying metadata, and writes readable PDFs with unchanged page counts.
