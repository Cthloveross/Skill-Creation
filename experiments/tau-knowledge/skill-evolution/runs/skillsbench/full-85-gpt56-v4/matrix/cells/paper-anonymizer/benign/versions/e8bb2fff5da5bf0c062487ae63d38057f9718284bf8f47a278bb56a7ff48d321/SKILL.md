---
name: precise-pdf-blind-review-anonymizer
description: Create blind-review PDF copies by manually discovering identity-bearing strings, then applying only exact PyMuPDF search-and-redact annotations while preserving pages, layout, scientific content, and bibliographic references.
---

# Precise PDF Blind-Review Anonymizer

Use this Skill for academic PDFs that must be anonymized without reconstructing, deleting, or broadly masking their content. It produces a copy with the same pages and layout, with only explicitly reviewed identity leaks removed.

## Safety rules

- Do **not** redact a visual area, delete pages, rasterize pages, or regenerate a PDF from extracted text.
- Do **not** use automatic name/entity detection or redact broad regex matches. Every page redaction must derive from an exact, human-reviewed target string.
- Leave the References/Bibliography section intact, including author names, DOIs, and arXiv IDs belonging to cited works. Targets found above a References heading, including headers on the first references page, can still be redacted.
- Do not target surname fragments. Target complete names and exact affiliation/identifier strings.
- Run discovery completely before invoking `scripts/redact_pdf.py`. The script intentionally cannot infer acknowledgement names or authors for the executor.

## Runtime prerequisites

Python 3 and PyMuPDF (`fitz`) must be installed. No network access is needed.

## 1. Discover each PDF manually

Use the inspection helper to obtain page-separated text, the first apparent References location, and standard metadata:

```bash
python3 scripts/inspect_pdf.py /root/paper1.pdf > /root/paper1-inspection.json
```

Read the `pages[].text` values—not merely the first page—and examine the rendered PDF too if extraction is garbled. Before writing a configuration, make a concrete list for that one document of:

1. Full author names in the byline, running headers/footers, contribution notes, and body prose.
2. Each author affiliation, lab/company name, address when identifying, email address, and correspondence note that names a person.
3. Every named person in acknowledgements and author-linked contribution statements. Also target the exact role label when a visible byline marker links it to authorship (for example, an equal-contribution or corresponding-author note). Preserve the surrounding acknowledgement sentences.
4. The paper's own arXiv identifier, DOI, venue/acceptance statement, and similar public lookup identifiers when they occur outside references.
5. Identity-bearing metadata values. Inspect `metadata` and `xml_metadata_present`; author/creator metadata is scrubbed by default, while other identity-bearing metadata fields must be explicitly selected.

Inspect every occurrence and add format variants as distinct strings when required (for example, a full and abbreviated affiliation). `search_for` needs an exact string as represented in the PDF. If a visual string is split by PDF encoding and the complete string has no match, use only uniquely reviewed exact searchable pieces that together remove the identifier; validate each piece's page and match count so a short fragment cannot remove unrelated scientific text.

Do not add authors solely because they occur in citations. The `non_references` scope handles an author who is both a byline author and cited in References.

## 2. Write a reviewed configuration

Create JSON such as `/root/paper1-redaction.json`. Values below are schema placeholders, not strings to reuse:

```json
{
  "input": "/root/paper1.pdf",
  "output": "/root/redacted/paper1.pdf",
  "targets": [
    {"text": "reviewed complete person name", "scope": "non_references", "required": true},
    {"text": "reviewed affiliation", "scope": "non_references", "required": true},
    {"text": "reviewed@example.invalid", "scope": "all", "required": true},
    {"text": "arXiv:YYMM.NNNNN", "scope": "non_references", "required": true}
  ],
  "metadata_keys": ["author", "creator"],
  "clear_xmp_metadata": true
}
```

Input schema:

- `input`, `output`: PDF paths.
- `targets`: nonempty reviewed list. Each target has exact nonempty `text`; `scope` is `all` or `non_references` (default); and `required` defaults to `true`.
- `non_references` excludes matches at and below the first detected References/Bibliography heading, but permits a running header above that heading. Use `all` only for a target that must be removed even if it appears in a citation.
- `metadata_keys`: standard metadata keys to blank. `author` and `creator` are always blanked, even if omitted. Add any field whose reviewed value leaks identity. Standard keys are `title`, `author`, `subject`, `keywords`, `creator`, `producer`, `creationDate`, `modDate`, `trapped`, `format`, and `encryption`.
- `clear_xmp_metadata`: defaults to `true`; it removes XMP metadata, which can duplicate authorship metadata. This does not alter page content.

Only set `required: false` for a deliberately optional visual variant. A required target with zero eligible matches is an error: revisit inspection or correct the exact PDF text rather than silently producing an incomplete result.

## 3. Apply exact redactions

```bash
mkdir -p /root/redacted
python3 scripts/redact_pdf.py < /root/paper1-redaction.json > /root/paper1-redaction-report.json
```

The script uses `page.search_for`, adds a separate redaction annotation for each returned rectangle, and applies the annotations page-by-page. It modifies the existing document and writes the requested output. It never chooses a region based on coordinates or regex.

Repeat discovery, reviewed configuration, and redaction separately for every input PDF; do not reuse one paper's discovered strings for another. For the requested three-paper workflow, outputs should be `/root/redacted/paper1.pdf`, `/root/redacted/paper2.pdf`, and `/root/redacted/paper3.pdf`.

## 4. Verify before delivery

`redact_pdf.py` automatically reopens the output and checks page count, absence of every target in its eligible scope, and expected metadata clearing. Treat any `ok: false` report as a failed deliverable.

Also run the independent verifier:

```bash
python3 scripts/verify_pdf.py < /root/paper1-redaction.json > /root/paper1-verification.json
```

It reports target remnants, page count, metadata status, and a conservative token-loss estimate. Review the output PDF visually around every changed location. A large number of non-target tokens missing, an unexpected page-count change, a target remnant, or an unmatched required target requires revisiting the reviewed target list/configuration. Ensure the output retains abstract, body, figures, equations, captions, acknowledgements prose, and the complete bibliography.

The report is an audit aid, not a substitute for reading acknowledgement prose and checking all document pages during discovery.
