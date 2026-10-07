---
name: blind-pdf-anonymization
description: Create faithful blind-review copies of supplied academic PDFs. Use when author names, affiliations, emails, acknowledgements, contribution notes, own-paper arXiv/DOI/venue leaks, running headers, or PDF metadata must be removed without deleting scientific content or bibliography.
---

# Blind PDF anonymization

This Skill modifies copies with true PDF redaction annotations. Every annotation is created only from a concrete exact-string `page.search_for()` result and then applied. It never draws an overlay or redacts an arbitrary rectangular page region.

It requires Python and PyMuPDF (`fitz`) in the execution runtime; it has no network dependency.

For the current task, create exactly these files:

- `/root/redacted/paper1.pdf` from `/root/paper1.pdf`
- `/root/redacted/paper2.pdf` from `/root/paper2.pdf`
- `/root/redacted/paper3.pdf` from `/root/paper3.pdf`

## Required workflow

### 1. Discover and review concrete identity leaks

Run the discovery helper on the pristine inputs:

```sh
python scripts/discover.py <<'JSON' > /root/discovery.json
{"inputs":["/root/paper1.pdf","/root/paper2.pdf","/root/paper3.pdf"]}
JSON
```

Read the returned page text, not just the automatically reported candidates. Review every title/byline, author footnote, header/footer, acknowledgement and contribution statement, and all text before the References heading. Build exact strings for:

- author names and affiliations;
- institutional/personal email addresses and correspondence notes;
- named people in acknowledgements;
- author-linked contribution notes;
- the submitted paper's own arXiv ID, DOI, accepted/published venue statement, or other public identifier;
- repeating author/identifier headers and footers; and
- identifying Author, Title, Subject, Keywords, or Creator metadata.

Leave bibliography entries and self-citations intact. In particular, names, arXiv IDs, and DOIs in References normally identify cited work, not the submitted paper. If a header on a References page repeats an identity leak, limit that target with a header/footer `regions` filter rather than searching the whole page.

### 2. Produce the three outputs

The task entrypoint always uses the exact required source/output paths, creates `/root/redacted`, and applies a conservative baseline of searchable direct identifiers, title-page affiliation material, metadata author values, own pre-References IDs, and likely acknowledgement names. Supply the reviewed targets as an object keyed by input filename. Targets discovered by reading are important because names in prose and unusual contribution notes cannot safely be inferred with regex alone.

```sh
python scripts/anonymize_task.py <<'JSON' > /root/anonymization-report.json
{
  "auto_discover": true,
  "targets": {
    "paper1.pdf": [
      {"text":"reviewed exact author name", "scope":"before_references"},
      {"text":"reviewed acknowledgement name", "scope":"before_references"}
    ],
    "paper2.pdf": [],
    "paper3.pdf": []
  }
}
JSON
```

`auto_discover` defaults to `true`. Run this from the original PDFs whenever targets change; do not redact an already-redacted output. The entrypoint emits one JSON report per required output and exits nonzero if any document cannot be validated.

A target object has:

- `text`: required nonempty exact source string. Use full names, never an isolated surname.
- `scope`: `before_references` (default), `pages`, or `all`.
- `pages`: one-based page list; required when `scope` is `pages`.
- `regions`: optional filters of the form `{"page": 3, "rect": [x0,y0,x1,y1]}`. A region only filters matching search results; it is never itself redacted.
- `required`: defaults to `true`. A required string with no eligible exact match fails rather than silently producing an incomplete PDF.

Use `before_references` for normal submitted-paper identity material. Use `all` only when every occurrence must be removed. For an identity string in a repeated header/footer that also occurs in the bibliography, use `scope: "all"` plus narrow `regions` for the header/footer matches.

For a reusable invocation, `scripts/anonymize.py` accepts:

```json
{"documents":[{"input":"source.pdf","output":"redacted.pdf","auto_discover":true,"clear_metadata":true,"targets":[{"text":"exact text","scope":"before_references"}]}]}
```

and writes `{"documents":[...],"valid":true}` to stdout.

### 3. Validate before delivery

The redactor verifies that the output opens as a PDF, has the original page count, no selected target remains at a selected match location, identity metadata is cleared, and no more than 50 non-target extracted words disappear. It writes output atomically only after those checks pass.

Open all three resulting files and inspect `/root/anonymization-report.json`. Confirm that title, abstract, body, equations, figures, tables, and bibliography remain readable; that no author or affiliation material remains; and that all three exact required paths exist. If a leak remains, add only its exact concrete string (and a page/region filter where needed) and rerun from the original source.

## Script interfaces and failure modes

All packaged scripts read one JSON object from stdin and emit JSON on stdout. Invalid JSON/schema, missing source PDF, unavailable PyMuPDF, absent required target, unreadable PDF, page-count change, unremoved selected target, remaining identifying metadata, or excessive non-target text loss produces a JSON error on stderr and a nonzero exit status.

- `scripts/discover.py`: input `{"inputs":["source.pdf", ...]}`; output includes extracted per-page text, metadata, References boundary, and review candidates.
- `scripts/anonymize.py`: input `{"documents":[document, ...]}`; output reports concrete targets, redaction counts, validation values, and warnings.
- `scripts/anonymize_task.py`: task-specific input shown above; writes the required three output files and reports their validation results.
