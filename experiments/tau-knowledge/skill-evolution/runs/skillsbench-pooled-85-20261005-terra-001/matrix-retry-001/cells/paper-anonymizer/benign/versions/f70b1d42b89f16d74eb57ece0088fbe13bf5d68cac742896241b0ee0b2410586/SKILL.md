---
name: blind-pdf-anonymizer
summary: Create true-redacted, same-page-count PDFs suitable for blind academic review.
description: Use when supplied academic PDFs must have authorship information removed while retaining scientific text, figures, page structure, and bibliography entries. The batch entrypoint writes anonymized copies and a JSON audit.
---

# Blind PDF anonymization

Run the batch entrypoint against the supplied PDFs. **Execute this command**; inspecting the script alone does not create the required artifacts.

```bash
python scripts/anonymize_batch.py <<'JSON'
{
  "inputs": ["/root/paper1.pdf", "/root/paper2.pdf", "/root/paper3.pdf"],
  "output_dir": "/root/redacted",
  "report_path": "/root/redacted/anonymization-audit.json"
}
JSON
```

For this task the required delivered files are exactly:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

The entrypoint uses PyMuPDF true-redaction annotations. It retains the original document pages instead of rebuilding PDFs from extracted text, preserving figures, equations, layout, scientific prose, and page count.

## Method

The script extracts text from every page, locates the References/Bibliography boundary, and builds an audit list of concrete exact strings found before that boundary. It detects title-block author-like strings and affiliations, emails, arXiv IDs, DOIs, acknowledgement-context names, correspondence/contribution lines, and explicit accepted/publication statements. It also clears PDF authoring metadata and XMP metadata.

Each removal is based on an exact `page.search_for()` result followed by `add_redact_annot()` and `apply_redactions()`. It never masks a guessed area or overlays a visual rectangle. Default targets are limited to content before References, including repeated headers and footers on earlier pages, so bibliography entries and self-citations remain intact.

Review the emitted audit and inspect unusual title blocks, acknowledgements, footnotes, and headers. If an identity string was missed, rerun with `targets_by_input`; use exact reviewed full strings, not an isolated surname. Do not redact names, arXiv IDs, or DOIs that occur solely in bibliographic references.

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact acknowledged person", "scope": "before_references"},
      {"text": "paper-owned repeated identifier", "scope": "pages", "pages": [0, 4]},
      {"text": "reviewed all-page leak", "scope": "all"}
    ]
  }
}
```

## JSON interface and validation

`scripts/anonymize_batch.py` reads one JSON object on stdin and emits one JSON object on stdout.

- Required `inputs`: nonempty array of existing PDF path strings.
- Required `output_dir`: destination directory; each output uses its input basename.
- Optional `targets_by_input`: mapping from an input-path string to arrays of exact target objects.
- Optional `report_path`: path for the UTF-8 audit JSON.

A target has nonempty `text` plus `scope`: `before_references` (default), `pages` with zero-based `pages`, or `all` only for a reviewed paper-owned repeated leak. The program creates parent directories, never modifies source PDFs, and returns nonzero JSON error output for invalid requests or unreadable inputs.

Before delivery, use the audit to confirm every job is readable and `page_count_matches` is true. Reopen delivered PDFs and confirm reviewed targets no longer extract as text. Compare source and output text: removals should be limited to the audited identity strings; scientific content and bibliography must remain substantially unchanged.
