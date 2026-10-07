---
name: blind-pdf-anonymization
description: Create blind-review versions of academic PDFs through exact-match, applied PDF redactions. Use for removing author names, affiliations, emails, acknowledgement names, own-paper arXiv/DOI/venue leaks, running headers, and identifying metadata while preserving pages, references, layout, and scientific content.
---

# Blind PDF anonymization

Use this Skill to produce redacted copies, never modify the supplied PDFs in place. It uses PyMuPDF (`fitz`) and only adds redaction annotations for rectangles returned by `page.search_for()` for a concrete discovered string, then applies them. It does not draw visual overlays or redact arbitrary page regions.

The supplied artifact task requires these outputs:

- `/root/redacted/paper1.pdf` from `/root/paper1.pdf`
- `/root/redacted/paper2.pdf` from `/root/paper2.pdf`
- `/root/redacted/paper3.pdf` from `/root/paper3.pdf`

## Required workflow

### 1. Discover and inspect

Extract all pages and metadata first. The discovery report is evidence for a human/executor review, not an automatic permission to delete prose.

```sh
python scripts/discover.py <<'JSON' > /root/discovery.json
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"]}
JSON
```

Read the report page by page. Inspect all title material, author/correspondence notes, headers and footers, acknowledgements, contribution notes, pre-reference pages, and metadata. Record exact strings for:

- full author names and affiliations;
- email addresses and correspondence information;
- names mentioned in acknowledgements or author-linked contribution statements;
- the submitted paper's own arXiv ID, DOI, acceptance notice, or venue identifier; and
- author names or own identifiers repeated in headers/footers.

Do not target author names, DOIs, or arXiv IDs occurring solely in bibliographic references. References and self-citations are retained.

### 2. Produce the requested files

The redactor's `auto_discover` mode supplies a conservative baseline from runtime PDF content: exact emails, arXiv IDs, DOIs before References, affiliation lines in title material, metadata authors, acknowledgement thank-you names, likely byline names, and acceptance/venue clue lines. It also clears document-info and XMP identity metadata. It still uses only concrete strings and `search_for()` results.

Run this task-specific invocation to create all declared artifacts:

```sh
python scripts/anonymize.py <<'JSON' > /root/anonymization-report.json
{
  "documents": [
    {"input":"/root/paper1.pdf","output":"/root/redacted/paper1.pdf","auto_discover":true},
    {"input":"/root/paper2.pdf","output":"/root/redacted/paper2.pdf","auto_discover":true},
    {"input":"/root/paper3.pdf","output":"/root/redacted/paper3.pdf","auto_discover":true}
  ]
}
JSON
```

The report lists every target, its selected-match count, unmatched automatic candidates, page count, and preservation result. Automatic detection cannot reliably understand all human names in prose. After reviewing `discovery.json`, add every missed concrete string as an explicit target and rerun from the original PDFs. For example:

```json
{
  "documents": [{
    "input": "/root/paper1.pdf",
    "output": "/root/redacted/paper1.pdf",
    "auto_discover": true,
    "targets": [
      {"text": "Exact Full Name", "scope": "before_references"},
      {"text": "Exact acknowledgement name", "scope": "before_references"},
      {"text": "Accepted at Exact Venue", "scope": "before_references"}
    ]
  }]
}
```

`targets` schema:

- `text`: required nonempty exact text. Use full names, not isolated surnames.
- `scope`: `before_references` (default), `pages`, or `all`.
- `pages`: optional one-based page list. It narrows any scope; `scope: "pages"` requires it.
- `regions`: optional filters of the form `{"page": 3, "rect": [x0,y0,x1,y1]}`. These filter exact search hits, such as a known running-header hit; they never redact the supplied rectangle directly.
- `required`: default `true`. A required target with no eligible exact match aborts before output replacement.

Use `before_references` for ordinary identity leaks. Use `all` only when every occurrence is intended for removal. For an author leak in a References-page header, use an explicit narrow `regions` filter around its known header match rather than deleting bibliographic occurrences.

### 3. Validate before delivery

The script writes to a temporary file, checks that page count is unchanged, checks that all selected match rectangles no longer contain their target strings, checks cleared identity metadata, and rejects outputs where over 50 non-target word tokens disappeared. It atomically installs the output only after validation.

Manually inspect the PDFs and report as a final safety check. Confirm that all three required `/root/redacted/paper*.pdf` files exist, retain every source page, retain abstract/body/figures/tables/equations and references, and have no direct or indirect author leak. If validation or review fails, correct only the exact target list or scope and rerun from the original input.

## Script interfaces

Both scripts read JSON from stdin and write JSON to stdout. Errors are JSON on stderr and return nonzero. They require Python and PyMuPDF, need no network access, and operate only on supplied paths.

- `scripts/discover.py`: input `{"inputs":["pdf-path", ...]}`; output contains extracted page text, metadata, reference boundaries, and review candidates.
- `scripts/anonymize.py`: input `{"documents":[document, ...]}`; each document requires `input` and `output`, and may supply `auto_discover`, `clear_metadata`, and `targets`; output contains one validation report per document.
