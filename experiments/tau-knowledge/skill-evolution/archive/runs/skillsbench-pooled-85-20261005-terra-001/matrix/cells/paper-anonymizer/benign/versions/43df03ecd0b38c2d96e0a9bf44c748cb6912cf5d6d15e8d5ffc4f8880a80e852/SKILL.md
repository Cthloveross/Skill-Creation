---
name: blind-pdf-anonymization
description: Produce structurally faithful blind-review PDF copies by discovering authorship leaks in supplied academic PDFs and applying irreversible, exact-text PDF redactions. Use for author names, affiliations, emails, acknowledgements, contribution notes, own-paper arXiv/DOI/venue leaks, running headers, and identifying metadata while retaining references and scientific content.
---

# Blind PDF anonymization

Use this Skill to create redacted copies rather than editing supplied PDFs in place. It requires Python with PyMuPDF (`fitz`) and has no network dependency. Redactions are added **only** to rectangles returned by `page.search_for()` for concrete strings, then applied; it never covers an arbitrary page region with an overlay.

For this task, produce exactly:

- `/root/redacted/paper1.pdf` from `/root/paper1.pdf`
- `/root/redacted/paper2.pdf` from `/root/paper2.pdf`
- `/root/redacted/paper3.pdf` from `/root/paper3.pdf`

## 1. Discover concrete leaks

First extract a review report. Read every page represented in the report, especially title/byline material, headers and footers, author notes, acknowledgement and contribution sections, and text before References.

```sh
python scripts/discover.py <<'JSON' > /root/discovery.json
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"]}
JSON
```

Build a concrete target list for each source. Include full author names, affiliations, emails, named people in acknowledgement prose, correspondence/contribution text that identifies an author, and the submitted paper's own arXiv ID, DOI, accepted-venue notice, or running-header identity leak. Metadata is also reported.

Keep the bibliography and self-citations. In particular, do not target author names, arXiv IDs, or DOIs merely because they occur in References. A name in a running header on a References page is an exception: target it with an explicit header region filter, not with an all-page text replacement.

## 2. Create all required PDFs

The redactor's `auto_discover` mode identifies a conservative baseline of concrete, searchable targets at runtime: title-page byline candidates and affiliations, emails, own pre-reference arXiv/DOI strings, acknowledgement thank-you names, acceptance/venue clues, metadata author values, and direct identifiers repeated in page headers or footers. It also clears PDF document-info and XMP metadata.

Run the following invocation from the task workspace. It creates the output directory as needed and installs each output atomically only after its validation succeeds.

```sh
python scripts/anonymize.py <<'JSON' > /root/anonymization-report.json
{
  "documents": [
    {"input":"/root/paper1.pdf", "output":"/root/redacted/paper1.pdf", "auto_discover":true},
    {"input":"/root/paper2.pdf", "output":"/root/redacted/paper2.pdf", "auto_discover":true},
    {"input":"/root/paper3.pdf", "output":"/root/redacted/paper3.pdf", "auto_discover":true}
  ]
}
JSON
```

Automatic discovery is not a substitute for reading acknowledgement prose and unusual author notes. Add every reviewed missed string as a manual target and rerun from the **original** input PDFs:

```json
{
  "documents": [{
    "input":"/root/paper1.pdf",
    "output":"/root/redacted/paper1.pdf",
    "auto_discover":true,
    "targets":[
      {"text":"Exact Full Author Name", "scope":"before_references"},
      {"text":"Exact acknowledgement name", "scope":"before_references"},
      {"text":"Accepted at Exact Venue", "scope":"before_references"}
    ]
  }]
}
```

Target fields are:

- `text` (required): a nonempty exact source string. Use full names, never a lone surname.
- `scope`: `before_references` (default), `pages`, or `all`.
- `pages`: optional one-based page numbers; required for `scope: "pages"`.
- `regions`: optional match filters, each `{"page": 3, "rect": [x0,y0,x1,y1]}`. A region only selects a `search_for()` match; it is never itself redacted.
- `required`: defaults to `true`. A required target with no eligible exact hit stops that document without replacing its existing output.

Use `before_references` for normal identifying material. Use `all` only if every occurrence is intended for removal. When a target appears in a bibliography as well as a known header/footer, use a narrow `regions` filter for the header/footer occurrence.

## 3. Verify before delivery

`scripts/anonymize.py` validates readable output, unchanged page count, removal of all selected text rectangles, cleared identity metadata, and a conservative non-target word-loss limit. It permits a PDF with no searchable candidates so that an already anonymous or image-only source can still be copied with metadata cleanup, but reports that condition for manual inspection.

Before completion, inspect `/root/anonymization-report.json` and open all three PDFs. Confirm that all three paths exist, pages/figures/equations/abstract/body remain, no identity leak remains, and References remain intact. If a leak is found, add only its exact concrete string or a match filter and rerun from the pristine source.

## Script interfaces

Both scripts read one JSON value from stdin and write JSON to stdout. On malformed input, missing source, unavailable PyMuPDF, unsearchable required target, or failed validation, they write a JSON error to stderr and exit nonzero.

- `scripts/discover.py` input: `{"inputs":["source.pdf", ...]}`. Output: page text, metadata, a detected References boundary, and candidates to review.
- `scripts/anonymize.py` input: `{"documents":[document, ...]}`. Each document has `input`, `output`, optional `auto_discover`, optional `clear_metadata`, and optional `targets`. Output lists targets, selected redaction counts, validations, and warnings per created PDF.
