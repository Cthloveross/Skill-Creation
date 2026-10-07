---
name: blind-pdf-anonymization
description: Perform surgical, true redaction of authorship-identifying information from academic PDFs for blind review while preserving pages, references, layout, and scientific content. Use for PDFs requiring removal of author blocks, affiliations, emails, acknowledgements names, own-paper arXiv/DOI/venue leaks, running headers, and identifying metadata.
---

# Blind PDF anonymization

This Skill uses PyMuPDF (`fitz`) to make irreversible text-level PDF redactions. It deliberately separates **discovery** from **redaction**: pattern detection can find candidate emails and identifiers, but an executor must read the extracted text and explicitly select all names and identity leaks before any PDF is modified.

For the supplied task, inspect all three supplied PDFs and configure one document entry per source, with its requested `/root/redacted/...` destination. Create `/root/redacted` as needed. Do not modify the inputs in place.

## Safety rules

- Redact only a concrete `text` string that was manually discovered in that PDF and confirmed searchable by `page.search_for()`.
- Never redact an area, title-page region, entire acknowledgement, section, isolated surname, or regex match wholesale.
- Inspect every page. Running headers, footers, footnotes, and acknowledgements are common leaks.
- Preserve the References/Bibliography section, including author names, self-citations, cited arXiv IDs, and cited DOIs. The default `before_references` scope excludes it.
- Redact the paper's own arXiv/DOI/venue or acceptance statement only where it occurs outside References.
- Names occurring in acknowledgements, contribution notes, affiliation/correspondence notes, and body self-identification must be explicit targets. Preserve surrounding prose.
- The redactor clears PDF document-info and XMP metadata because Author/Creator metadata can itself reveal authorship. It otherwise edits the existing PDF and keeps its page count unchanged.

## 1. Discover and review content

Run `scripts/discover.py` once over the supplied source paths. It reads all pages and emits JSON containing page text, document metadata, detected reference boundary, and *candidate* emails/arXiv IDs/DOIs/venue-like lines. Candidates are evidence to review, not a redaction list.

```sh
python scripts/discover.py <<'JSON' > discovery.json
{"inputs":["/path/to/input-a.pdf","/path/to/input-b.pdf"]}
JSON
```

Read `discovery.json` page by page. In particular, manually read the first-page author block, all acknowledgement and contribution text, headers/footers, and all pre-reference pages. Record exact full strings for author names, affiliations, emails, named people, correspondence text tied to people, and own-paper identifiers. Check metadata too; it will be cleared by the redactor.

The report's `reference_boundary` has a page number and y-coordinate. A heading detected part way down a page means content above it remains eligible for `before_references`; reference material below it does not.

If a name or identifier is visually present but is not found by `search_for`, inspect the extracted spelling and add a searchable exact variant (for example, PDF hyphenation or Unicode normalization may differ). Do not replace this with a broad substring or region redaction.

## 2. Write an explicit configuration

Create a JSON configuration such as the schema below. All names from prose must be written explicitly after review; the scripts never infer person names automatically.

```json
{
  "documents": [
    {
      "input": "/path/to/input.pdf",
      "output": "/path/to/redacted.pdf",
      "clear_metadata": true,
      "targets": [
        {"text": "Exact full person name", "scope": "before_references"},
        {"text": "Exact affiliation", "scope": "before_references"},
        {"text": "person@example.edu", "scope": "before_references"},
        {"text": "arXiv:0000.00000", "scope": "before_references"},
        {"text": "Accepted at Exact Venue", "pages": [1], "scope": "pages"}
      ]
    }
  ]
}
```

Target fields:

- `text` (required): one nonempty, exact string. Full names are safer than surnames.
- `scope` (optional): `before_references` (default), `pages`, or `all`. `before_references` includes pages before the reference heading and only the area above the heading on its page. It is the normal choice for bylines, body leaks, and own-paper identifiers. `all` must only be used when every occurrence is intended for redaction and cannot damage a citation.
- `pages` (optional): one-based page numbers; this additionally narrows the scope. Use it for an unambiguous title-page or header occurrence.
- `regions` (optional): an additional narrow filter, e.g. `[{"page": 8, "rect": [0, 0, 612, 55]}]`, for a repeated header on a References page. It accepts only search matches intersecting one of those explicit rectangles; it does not redact the rectangle itself.
- `required` (optional, default `true`): the run fails if no eligible exact match exists. Keep this enabled so spelling/scope errors cannot silently leave leaks.

If there is no detected References heading, do not use `before_references` unless the document truly has no references. Use reviewed `pages` and/or narrow `regions` instead, so a bibliography cannot be accidentally altered.

## 3. Redact and validate

Run the end-to-end script with the reviewed configuration on stdin:

```sh
python scripts/anonymize.py < redaction-config.json > anonymization-report.json
```

For each target, the script calls `page.search_for(text)`, filters only the selected exact matching rectangles, adds a redaction annotation to each rectangle, and applies annotations page by page. It aborts if a required target has no selected match. It saves to a temporary file, validates it, then atomically places it at the requested output path.

Validation checks that page count is unchanged, all selected target locations no longer contain the target text, document identity metadata fields are blank when requested, and no more than 50 non-target word tokens disappeared. A validation failure is an unsafe result: correct the explicit target spelling or scope and rerun from the original input. Review `anonymization-report.json` and manually inspect the resulting PDFs before delivery.

The scripts require Python plus PyMuPDF. They read JSON from stdin and write JSON to stdout; errors are written to stderr with a nonzero exit status. No network access or PDF reconstruction is used.
