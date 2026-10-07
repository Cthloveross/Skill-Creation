---
name: blind-review-pdf-anonymizer
description: Create page-preserving, truly redacted academic PDFs for blind review. Use for supplied PDFs that need authors, affiliations, emails, acknowledgements, headers/footers, preprint or publication leaks, and identifying metadata removed while retaining scientific content and the bibliography.
---

# Blind-review PDF anonymizer

This Skill **creates the requested artifacts**. Do not stop after identifying leaks or producing a report. Run the entrypoint, then ensure every requested output PDF exists.

For the current task, run this from the Skill package directory:

```bash
python scripts/anonymize_batch.py <<'JSON'
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"],"output_dir":"/root/redacted","report_path":"/root/redacted/anonymization-audit.json"}
JSON
```

The required deliverables are exactly:

- `/root/redacted/paper1.pdf`
- `/root/redacted/paper2.pdf`
- `/root/redacted/paper3.pdf`

## Procedure

1. Read the produced audit. The program extracts text from all source pages, finds the References/Bibliography boundary, and constructs precise candidate strings before that boundary.
2. Review title blocks, acknowledgements, correspondence/contribution notes, headers/footers, and disclosure text for any concrete identity leak missed by the automatic discovery. Rerun the affected PDF with exact reviewed strings in `targets_by_input`; do not use broad rectangular/page redactions or isolated surnames.
3. The program uses PyMuPDF search results, redaction annotations, and `apply_redactions()`. Thus removed text is not merely covered by a visual box and is no longer text-extractable.
4. It preserves page count and leaves the bibliography outside automatic redaction scope. Names, DOIs, arXiv IDs, and self-citations belonging to bibliographic entries must remain.
5. Before completion, confirm all three output files exist, open successfully, retain their source page counts, and have no `residual_targets_before_references` or `unmatched_manual_targets` in the audit.

The script removes title/byline candidates, affiliation lines, emails, preprint identifiers, DOIs, acknowledgement names following common acknowledgement constructions, exact correspondence/contribution disclosures, and exact acceptance/publication/venue disclosures. It also clears PDF document and XMP metadata, including Author. Automatic matching is deliberately limited to exact extracted strings rather than regions.

### Supplying reviewed targets

Use this JSON shape when an unusual leak requires a reviewed exact target:

```json
{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact acknowledgement name", "scope": "before_references"},
      {"text": "Exact repeated header", "scope": "pages", "pages": [0, 2]},
      {"text": "Exact identity disclosure", "scope": "all"}
    ]
  }
}
```

Never redact a whole acknowledgement section, title area, or page. Do not redact citations merely because they contain author names, a DOI, or an arXiv identifier.

## JSON interface

`scripts/anonymize_batch.py` reads one JSON object on stdin and emits one JSON object on stdout.

- `inputs` (required): nonempty list of existing source PDF paths.
- `output_dir` (required): destination directory. Each output uses the input basename.
- `targets_by_input` (optional): object mapping an exact input path to reviewed target arrays.
- `report_path` (optional): location to write the same audit JSON.
- A target has nonempty `text`, optional `scope` (`before_references`, `pages`, or `all`), and a nonempty zero-based `pages` array when scope is `pages`.

Invalid JSON, nonexistent input, invalid target/page, unavailable PyMuPDF, unreadable saved output, or changed page count returns an error JSON object and nonzero status. Source PDFs are never overwritten.
