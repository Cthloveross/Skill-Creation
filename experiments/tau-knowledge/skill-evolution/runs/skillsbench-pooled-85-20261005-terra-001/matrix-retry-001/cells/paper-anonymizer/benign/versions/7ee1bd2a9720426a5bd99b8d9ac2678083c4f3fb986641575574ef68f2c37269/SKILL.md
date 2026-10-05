---
name: blind-pdf-anonymizer
description: Create deliverable, same-page-count PDF copies for blind peer review by applying true text redactions to authorship leaks while preserving scientific content and the bibliography. Use when supplied academic PDFs must be saved at specified anonymized output paths.
---

# Blind-review PDF anonymization

This Skill produces the PDF artifacts; do not stop after inspecting files or describing a redaction plan. Run the packaged entrypoint once for the supplied files, then use its JSON result to confirm delivery:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

For the current task, completion requires all of the following files to exist and open as PDFs:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

The script creates `/root/redacted` itself, writes an output whose basename matches every input, and leaves source files unmodified. Its success JSON must report `readable: true` and `page_count_matches: true` for every job. If it reports an error, correct the supplied input paths or runtime dependency and rerun; an audit JSON or a visual overlay is not a substitute for the three PDFs.

## What the entrypoint does

For each PDF, it extracts every page before modifying it, finds the References/Bibliography boundary, and builds concrete redaction targets from text actually present in the document. It searches title matter, all pre-reference pages, headers/footers, footnotes, acknowledgement prose, and PDF metadata for:

- byline-like full names and affiliation lines;
- email addresses and correspondence/contribution notes;
- acknowledgement names following common acknowledgement constructions;
- the paper's own pre-reference arXiv identifiers, DOIs, and acceptance/publication statements; and
- identifying Author/Creator/XMP metadata.

Each removal is an exact `page.search_for()` match followed by a PyMuPDF redaction annotation and `apply_redactions()`. It does not redraw pages, delete pages, or merely paint opaque rectangles over extractable text. Candidate searches are limited to pre-reference content so bibliographic references, including self-citations and cited-paper identifiers, remain intact. Standard and XMP metadata are cleared without changing page structure.

The output audit includes each searched target, match count, and unmatched candidates. Review unmatched automatic candidates only if needed: PDF text encoding can prevent an exact match. For a reviewed leak missed by automatic discovery, supply it as a full concrete string (never a surname alone) via `targets_by_input` and rerun. Do not add identifiers that occur only in References.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Reviewed full acknowledgement name", "scope": "before_references"},
      {"text": "Recurring running-header identity leak", "scope": "all"},
      {"text": "Known leak on selected pages", "scope": "pages", "pages": [0, 2]}
    ]
  },
  "report_path": "/path/redacted/anonymization-audit.json"
}
```

## JSON interface

`scripts/anonymize_batch.py` reads exactly one JSON object from stdin and writes one JSON object to stdout.

- `inputs` (required): nonempty list of existing source-PDF paths.
- `output_dir` (required): destination directory. Each output uses the corresponding input basename.
- `targets_by_input` (optional): map from source path to an array of reviewed target objects.
- `report_path` (optional): location for the same structured audit emitted on stdout.

A target requires nonempty `text`. `scope` is `before_references` (default), `all`, or `pages`; `pages` additionally requires nonempty zero-based page indices. Invalid requests, unreadable input, failure to write a readable output, or changed page count cause a nonzero exit and an error JSON response.
