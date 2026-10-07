---
name: pdf-paper-anonymizer
description: Anonymize academic PDFs for blind peer review by discovering and removing author-identifying strings (names, affiliations, emails, arXiv IDs, DOIs, venue/acceptance statements, acknowledgement names) using precise string-level PyMuPDF redaction, while preserving the page count, references section, and all scientific content. Use when a task asks to redact/anonymize one or more PDF papers and save redacted copies.
---

# PDF Paper Anonymizer

Anonymization is a three-phase process: **discover** the exact identity-revealing strings
by reading each PDF, **redact** each string with precise string-level annotations
(never region/area blanking), and **verify** that targets are gone and content is preserved.

The critical rule: **every redaction must correspond to a specific text string**
found via `page.search_for(...)`. You must *read* the extracted text yourself to find
person names (author block, acknowledgements, contribution footnotes) — those do not
follow regex patterns. Pattern-findable items (emails, arXiv IDs, DOIs, venue phrases)
are surfaced automatically to help, but you still confirm them.

## Inputs / outputs for this task family

- Input PDFs are given at explicit paths (read the current task's opening/manifest, e.g.
  `/root/paper1.pdf`, `/root/paper2.pdf`, `/root/paper3.pdf`). Do not hardcode these;
  use whatever paths the current request supplies.
- Produce one redacted PDF per input at the requested output location (e.g.
  `/root/redacted/paper{1-3}.pdf`). Create the output directory if missing.
- Each output must have the **same page count** and substantially the same content as its
  input, differing only by the redacted identity strings.

## Prerequisites

Scripts require PyMuPDF. If import fails they emit a JSON error telling you to install it:
```
pip install pymupdf
```
Internet is allowed in this task environment. No external text tool is required —
verification uses PyMuPDF's own text extraction.

## Workflow

### Phase 1 — Discovery (read the PDF, build an explicit list)

For each input PDF run the extractor:
```
echo '{"pdf": "/root/paper1.pdf"}' | python3 /app/environment/skills/current/scripts/extract.py
```
(Use the actual skill directory from the environment; it is the directory containing this
SKILL.md. If unsure, locate the scripts with `find / -name extract.py -path '*skills*'`.)

The extractor outputs JSON with:
- `num_pages`, `metadata` (Author/Creator fields — read these for extra names),
- `references_boundary` (page index + y of the References/Bibliography heading, or null),
- `auto_candidates`: regex hits for `emails`, `arxiv`, `doi`, and `venue` hint lines
  (collected **before** the references section only),
- `pages`: full per-page text.

**Read `pages[0]` (title page) carefully** to list author names (full names as printed),
affiliations (including abbreviated variants, e.g. a full and a short institute name),
and any correspondence/contribution footnotes — copy their exact wording.
**Read the acknowledgements section** (search the page texts for "Acknowledg") sentence by
sentence and list every person name thanked (e.g. after "We thank", "grateful to",
"with the help of"). Acknowledgement names are the most commonly missed leakage and cannot
be found by regex — only by reading. Do NOT plan to blank the whole acknowledgements
section; list only the specific names/identifiers.

Confirm the `auto_candidates`: keep the paper's **own** arXiv ID / DOI / venue statement
(usually in a header, footer, or first page). Ignore arXiv IDs and DOIs that appear **inside
the references** — those belong to cited works and must not be redacted.

Finalize an explicit redaction list per PDF **before writing/running redaction**.
Each entry is either a plain string or an object `{"text": "...", "scope": "all"|"before_references"}`:
- Author names, affiliations, acknowledgement names, contribution footnotes, emails:
  default `scope` = `before_references` (protects self-citations in the reference list).
- The paper's own arXiv ID, DOI, and venue/acceptance line: use `scope` = `all`
  (these are exact strings; other papers' IDs differ, so matching everywhere is safe and
  catches running headers/footers on later pages).
Always list the **full discovered name**, never a bare surname token (a surname alone would
match unrelated citations and common words — over-redaction).

### Phase 2 — Redaction (string-level, page-by-page, in place)

Run the orchestrator with all jobs at once (it regenerates every output):
```
echo '{"jobs": [
  {"input": "/root/paper1.pdf", "output": "/root/redacted/paper1.pdf", "clear_metadata": true,
   "redactions": ["Full Author Name", "Second Author", "Example Research University",
                  "Example Research Univ.", "name@univ.edu", "Acknowledged Person",
                  {"text": "arXiv:2401.12345", "scope": "all"},
                  {"text": "10.1145/xxxxxxx", "scope": "all"},
                  {"text": "To appear in Proceedings of ExampleConf 2024", "scope": "all"}]},
  {"input": "/root/paper2.pdf", "output": "/root/redacted/paper2.pdf", "redactions": [ ... ]},
  {"input": "/root/paper3.pdf", "output": "/root/redacted/paper3.pdf", "redactions": [ ... ]}
]}' | python3 /app/environment/skills/current/scripts/anonymize.py
```
The orchestrator, per job: opens the PDF, locates the references boundary, searches every
page for each target string, adds a redaction annotation over each matching rectangle
(respecting `scope`), applies redactions (permanently removing the text from the content
stream), optionally clears the Author/Creator metadata fields, and saves with the **same
page count**. It never uses area/region redaction. Output JSON reports per-job match counts
per string and an inline verification summary.

### Phase 3 — Verification

The orchestrator runs verification automatically; you can also run it standalone:
```
echo '{"original": "/root/paper1.pdf", "redacted": "/root/redacted/paper1.pdf",
       "targets": ["Full Author Name", "arXiv:2401.12345", ...]}' \
  | python3 /app/environment/skills/current/scripts/verify.py
```
It reports:
- `remaining_targets`: any target string still present in the redacted text — these are
  under-redaction failures; investigate (the PDF may store the text with ligatures,
  hyphenation, or odd spacing so `search_for` missed it). Try a shorter/variant substring
  or split the string, add it to the list, and re-run.
- `page_count_ok`: output page count equals input — must be true.
- `extra_words_removed`: count of non-target words that vanished vs the original. If this is
  large (background threshold ~>50), redaction was too aggressive — likely a target string
  matched unintended text (e.g. a surname that is also a common word). Replace it with the
  full name or a more specific string.

Iterate: adjust the redaction list and re-run `anonymize.py` until, for every PDF,
`remaining_targets` is empty, `page_count_ok` is true, and `extra_words_removed` is small.

## Failure handling

- A target not found by `search_for` (appears in `remaining_targets` but you know it is in
  the text): the internal representation differs. Try matching a contiguous sub-span, or
  the token split across the hyphen/space, and add those variants.
- A string that must stay in references but gets removed: ensure its `scope` is
  `before_references` (the default) rather than `all`.
- If `references_boundary` is null (no heading found), `before_references` falls back to
  redacting on all pages; in that case prefer full exact name strings to avoid citation hits.
- Never delete pages, collapse sections, blank rectangular regions, or reconstruct the PDF
  from scratch; only string-level redaction is acceptable.

## Validation checklist before finishing

1. Each requested output PDF exists at its required path.
2. Each output `num_pages` equals its input.
3. `verify.py` shows empty `remaining_targets` and small `extra_words_removed` for each PDF.
4. The references section and body content remain intact.
