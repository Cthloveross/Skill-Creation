---
name: verify-bibtex-citations
description: Verify a supplied BibTeX bibliography for fabricated or mismatched academic citations. Use for tasks that require a sorted JSON list of fake citation titles, especially when DOI, Crossref, DataCite, Semantic Scholar, and DBLP evidence can be consulted.
---

# Verify BibTeX citations

This Skill audits the actual BibTeX file at runtime. It does not assume that a plausible title, a syntactically valid DOI, or a missing DOI establishes authenticity.

## Inputs and outputs

Run `scripts/audit_bibliography.py` with one JSON object on standard input:

```json
{"bib_path":"/root/test.bib","output_path":"/root/answer.json","audit_path":"/root/citation-audit.json"}
```

Optional input fields are:

- `timeout_seconds` (number, default `15`): timeout for each HTTP request.
- `manual_overrides` (object): maps a BibTeX citation key to `"fake"`, `"real"`, or `"unverified"`. Use this only after recording independent, authoritative evidence in the audit process.

The script writes:

- `output_path`: exactly `{"fake_citations":[...]}`. Titles are cleaned and alphabetically sorted.
- `audit_path`: an evidence report for every parsed entry, including source requests, metadata comparisons, status, and review notes.
- stdout: a small JSON execution summary.

All paths are runtime inputs; no bibliography-specific titles, keys, or answers are packaged in this Skill.

## Method

1. Run the audit script. It parses balanced BibTeX values rather than splitting blindly on commas, removes common LaTeX/BibTeX title markup, and retains each citation key for review.
2. For every DOI, query Crossref's exact DOI endpoint. If Crossref has no record, query DataCite because a valid non-Crossref DOI can occur there. Compare normalized title, author surnames, venue, year, volume, and pages when metadata is available.
3. For entries with no usable matching DOI, search Crossref by cleaned title and additionally search Semantic Scholar and DBLP by title. The audit records both positive matches and source/network failures.
4. Treat a DOI confirmed missing from both registries as strong fabrication evidence. Treat a DOI whose returned work has a radically different title as a likely fabricated/mismatched citation. A matching DOI record is strong evidence that the record is genuine.
5. Do **not** call an entry fake merely because a title search failed: coverage gaps, older material, books, and outages exist. Such items remain `unverified` unless independent evidence establishes fabrication. For those, query the claimed publisher/venue and, where appropriate, manually search Google Scholar or an institutional catalogue. Record the source and result before using a `manual_overrides` decision.
6. Inspect `citation-audit.json`, particularly `unverified`, `mismatched_doi`, and `error` statuses. If authoritative follow-up proves a citation fake, rerun with its citation key set to `fake` in `manual_overrides`. If it proves genuine, set it to `real`.
7. Deliver only the required `answer.json`; do not add rationale, citation keys, or uncertain entries to its `fake_citations` array. The script already sorts and deduplicates titles.

Example execution:

```sh
python3 /app/environment/skills/current/scripts/audit_bibliography.py <<'EOF'
{"bib_path":"/root/test.bib","output_path":"/root/answer.json","audit_path":"/root/citation-audit.json"}
EOF
```

## Validation

Before submission, validate that `/root/answer.json` parses as JSON, has exactly the `fake_citations` key, that its value is a list of strings, each string contains no BibTeX braces/backslashes, and the list is lexicographically sorted. The entrypoint performs these checks after writing. Also ensure the audit did not classify an entry as fake solely due to an HTTP/network error; those must remain review items.
