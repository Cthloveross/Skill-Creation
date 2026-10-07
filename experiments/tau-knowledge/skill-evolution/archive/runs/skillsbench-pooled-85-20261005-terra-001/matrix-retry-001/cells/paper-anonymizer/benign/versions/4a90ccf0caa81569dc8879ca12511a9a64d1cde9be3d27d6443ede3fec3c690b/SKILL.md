---
name: blind-pdf-anonymizer
description: Create and verify surgically redacted PDFs for blind review. Use when supplied PDFs must retain their pages, layout, scientific content, and references while removing authorship signals from text and selected metadata.
---

# Blind-review PDF anonymization

This Skill implements a **discover → explicitly plan → true-redact → verify** workflow. It uses PyMuPDF (`fitz`) and makes only text-search redactions: every redaction rectangle is returned by `page.search_for()` for an exact, human-reviewed string. It never masks a page region or reconstructs a PDF.

## Prerequisites and limits

* Python must be able to import `fitz` (PyMuPDF). The scripts report a JSON error if it is unavailable.
* Input PDFs must be readable and must contain searchable text for every planned target. A scanned name, logo, rasterized author block, encrypted PDF, or text with an unsearchable font representation needs appropriate OCR/manual remediation; do not substitute a broad rectangle.
* Use only the supplied PDF paths and required output paths at runtime. The scripts create output parent directories.
* `references_page` and `pages` in a redaction plan are **zero-based**. The inventory report displays both zero-based indexes and human-facing page numbers.

## 1. Discover before redacting

Create an inventory report for every supplied PDF. It contains full page-by-page extracted text, document information metadata, XMP metadata when available, a suggested References-page boundary, and pattern candidates. Pattern candidates are leads only; they are not a redaction list.

```bash
python scripts/pdf_inventory.py <<'JSON'
{"inputs":["/path/to/input-a.pdf","/path/to/input-b.pdf"],"report_path":"/path/to/anonymization-inventory.txt"}
JSON
```

Read the complete report and visually inspect pages where extraction is incomplete. Before creating a plan, identify exact strings for all of the following as applicable:

1. Each author name in the byline, running headers/footers, author-linked contribution notes, and prose outside bibliography entries.
2. Each affiliation, department/lab/company, postal address, personal or institutional email, correspondence note, and author-specific footnote.
3. Every named person in acknowledgements or contribution prose. Read these sentences; regex cannot reliably find names.
4. The paper's own arXiv identifier, DOI, accepted/published venue statement, or other public identifier in title matter, body, headers, or footers.
5. Identity-bearing PDF information/XMP metadata values, especially `author` and `creator`.

Do not infer final targets from the candidate regex output alone. Record each exact visible/extracted spelling separately, including meaningful variants. Do not redact isolated surnames or broad institution/category terms.

Determine and confirm the first page on which the References/Bibliography begins. Reference author names, reference DOIs, reference arXiv IDs, and self-citations must remain intact. For ordinary authorship strings use `before_references`; this protects bibliography pages. If an own identifier or author running header is also on a references page, use a narrowly selected `pages` target for that exact string after visual confirmation, rather than applying author-name redaction to all pages.

## 2. Make an explicit plan and apply true redactions

Supply a JSON plan to `scripts/redact_pdfs.py`. Each target must be an exact string discovered above and must have one of these scopes:

* `before_references`: pages before the job's confirmed `references_page`.
* `pages`: only the listed zero-based page indexes.
* `all`: all pages. Use only for a unique paper-owned identifier whose every occurrence is intended for removal; it is generally unsafe for names because references may contain them.

`expected_matches`, when supplied, is an additional guard and must equal the number of `search_for()` rectangles found in the selected scope. A target with zero matches, a scope error, or a count mismatch prevents that job from being written. This is intentional: resolve formatting/Unicode/line-break variants in the discovery phase instead of silently producing an incomplete PDF.

Example schema (the strings and paths below are placeholders, not targets):

```bash
python scripts/redact_pdfs.py <<'JSON'
{"jobs":[{"input":"/path/to/original.pdf","output":"/path/to/redacted.pdf","references_page":8,"targets":[{"text":"Exact Person Name","scope":"before_references"},{"text":"arXiv:1234.56789","scope":"pages","pages":[0,8]}],"metadata_clear":["author","creator"],"clear_xmp":true}]}
JSON
```

`metadata_clear` is a list of reviewed metadata keys to blank, chosen from `title`, `author`, `subject`, `keywords`, `creator`, `producer`, `creationDate`, `modDate`, and `trapped`. Clear only fields whose values reveal identity (normally at least reviewed author/creator fields). Set `clear_xmp` only after review when the XMP packet contains identity-bearing data. The script preserves all other PDF metadata values.

For the current task, make one job per supplied paper and pass its required destination path in `output`; do not alter the source PDF. The script writes via a temporary file and atomically replaces the destination only after all targets in that job were located and applied.

## 3. Verify the produced PDFs

Run verification using the **same reviewed job plan** (with its final target list and metadata settings):

```bash
python scripts/verify_redactions.py <<'JSON'
{"jobs":[{"input":"/path/to/original.pdf","output":"/path/to/redacted.pdf","references_page":8,"targets":[{"text":"Exact Person Name","scope":"before_references"}],"metadata_clear":["author","creator"],"clear_xmp":true}],"max_unexpected_missing_words":50,"report_path":"/path/to/verification-report.json"}
JSON
```

Verification checks that page count is unchanged, no target remains in its intended scope, selected metadata fields are blank, and a word-multiset comparison finds no more than the configured number of non-target words missing. It deliberately permits a target name/identifier to remain in untouched bibliography pages when the plan scope excludes those pages. Treat any failed check, unmatched string, or unexpected missing-word report as a reason to revise the explicit plan and recreate that output. Also visually inspect the final PDF, especially title material, acknowledgements, headers/footers, and pages containing References.

The scripts emit one JSON result object on stdout. Optional reports are UTF-8 files written to paths supplied in the JSON request.
