---
name: citation-check
description: >
  Verify a BibTeX bibliography and identify fake or hallucinated academic
  citations. Parses /root/test.bib, cleans LaTeX formatting from titles,
  verifies each entry using DOI resolution (CrossRef + doi.org), DOI registrant
  analysis, and title search in CrossRef/Semantic Scholar, then writes the
  cleaned titles of fake citations (alphabetically sorted) to /root/answer.json.
  Use whenever a task supplies a .bib file and asks which citations are fake.
---

# Citation Check: detecting fake / hallucinated references

## Task contract

- Input: a BibTeX file (default `/root/test.bib`) containing a mix of real and
  fabricated citations.
- Output: `/root/answer.json` of the exact form
  ```json
  {"fake_citations": ["Cleaned Title A", "Cleaned Title B"]}
  ```
  Only the **titles** of fake entries, cleaned of BibTeX/LaTeX formatting
  (`{}`, `\`, LaTeX commands, collapsed whitespace), **sorted alphabetically**.

## Verification method (combine signals, strongest first)

The method follows the frozen background's practical strategy. No single signal
is trusted alone; a decision is made per entry:

1. **DOI-first triage.** For an entry with a `doi` field, attempt to resolve it
   via the CrossRef works API (`https://api.crossref.org/works/<doi>`) and via a
   HEAD/GET to `https://doi.org/<doi>`.
   - Resolves on either → genuine (not fake).
   - Fails on both (404 / no redirect to a publisher page) → **fake**. An
     unresolvable DOI is the strongest single fabrication signal.
2. **Registrant analysis.** For a DOI that fails resolution, the unrecognized
   `10.XXXX` registrant code reinforces the fake verdict. Known publisher codes
   are listed in `references/registrants.txt`; an unknown registrant combined
   with failed resolution is treated as fake. Resolution still governs: a known
   registrant whose full DOI does not resolve is still suspect.
3. **Database cross-referencing (no DOI, or DOI inconclusive).** Clean the title
   and search CrossRef (`query.bibliographic`) and Semantic Scholar
   (`/graph/v1/paper/search`). A close normalized title match in either database
   → genuine. Confident absence from both (searches ran successfully and
   returned no matching title) → **fake**.
4. **Provenance.** Entries carrying DBLP `biburl`/`bibsource` or ACL Anthology
   provenance are strong genuine signals and are not marked fake on absence
   alone.

### Important distinctions (from background)

- A syntactically valid DOI is **not** necessarily registered — only resolution
  proves it.
- Minor title formatting differences are normal; normalize before comparing.
- "Cannot verify" is weaker evidence than "confirmed fake". When network lookups
  fail entirely for an entry (not a clean negative), do not fabricate a fake
  verdict from a network error — prefer leaving it out to avoid false positives,
  and note it in the script summary for manual review.
- Clean LaTeX from titles before any search or before writing the answer.

## How to run

Internet is permitted in this environment (`allow_internet: true`, bridge
network). Run the end-to-end entrypoint from the Codex terminal:

```bash
echo '{}' | python3 /app/environment/skills/current/scripts/verify.py
```

or with explicit paths:

```bash
echo '{"bib_path": "/root/test.bib", "out_path": "/root/answer.json"}' \
  | python3 scripts/verify.py
```

### Script I/O schema

`scripts/verify.py`
- **stdin** (JSON, all optional): `{"bib_path": str, "out_path": str,
  "offline": bool}`. Defaults: `bib_path=/root/test.bib`,
  `out_path=/root/answer.json`, `offline=false`.
- **side effect**: writes `out_path` with `{"fake_citations": [...]}` (cleaned,
  alphabetically sorted, de-duplicated).
- **stdout** (JSON): a report
  ```json
  {"out_path": "...", "num_entries": N, "fake_citations": [...],
   "details": [{"key": "...", "title": "...", "doi": "...",
                "verdict": "fake|real|unverified", "reason": "..."}]}
  ```

`scripts/parse_bib.py` is a helper exposing `parse_bibtex(text)` ->
list of dicts (`key`, `type`, fields...) and `clean_title(raw)` ->
cleaned title string. It is imported by `verify.py` and can be run standalone
(stdin `{"bib_path": "..."}` -> stdout list of parsed entries) for inspection.

## Interpreting results and completing the task

1. Run `verify.py`. Inspect the stdout `details` for each entry's verdict and
   reason.
2. Confirm `/root/answer.json` exists and contains a sorted, cleaned
   `fake_citations` list. Entries marked `unverified` (network failure, not a
   clean negative) are excluded by default — review them manually if the task
   demands completeness and re-run after connectivity is restored.
3. Spot-check a few DOIs manually (e.g. `curl -sI https://doi.org/<doi>`) if a
   verdict looks wrong, and re-run.

## Failure handling

- Missing bib file → script exits nonzero with an error message on stdout.
- Transient API errors are retried with backoff; a persistent failure for an
  entry yields an `unverified` verdict rather than a false `fake`.
- If the runtime lacks `requests`, the script falls back to urllib (stdlib).
- `offline: true` skips network checks and marks only DOIs with clearly unknown
  registrants plus malformed entries, labeling everything else `unverified`.
