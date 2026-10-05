---
name: verify-bibtex-citation-integrity
description: Verify a supplied BibTeX bibliography for likely fabricated or hallucinated citations. Use when the required deliverable is a JSON list of fake citation titles and network access to DOI registries and scholarly indexes is available.
---

# Verify BibTeX Citation Integrity

Use `scripts/verify_bibliography.py` against the BibTeX file supplied by the task. The script parses entries without requiring third-party Python packages, cleans BibTeX/LaTeX title formatting, and checks DOI-bearing entries before doing title searches for entries without a DOI.

## Method

1. For each DOI, query Crossref and DataCite and attempt DOI resolution. When registry metadata is found, compare its title with the entry title after normalization.
2. A DOI that is absent from both registries **and** fails resolution is classified as a strong fake signal. A registered DOI whose metadata title strongly conflicts with the BibTeX title is also classified as a likely fabricated/misattributed citation.
3. For entries without a DOI, query Crossref, OpenAlex, and Semantic Scholar by cleaned title. An academic article/proceedings entry is classified only when all three sources successfully answered and none had a strong title match. This deliberately leaves one-source failures and incomplete coverage as `needs_review`, rather than calling them fake.
4. The script writes the task-required JSON artifact and a separate audit trail. The required artifact contains only sorted, cleaned titles selected by the strong rules above.

Do not treat a plausible DOI format, a generic-sounding title, or a missing result from one index as proof of fabrication. Network/API errors are recorded separately from legitimate `not found` responses.

## Runnable call

The script receives one JSON object on stdin and emits a JSON execution summary on stdout:

```bash
python3 scripts/verify_bibliography.py <<'JSON'
{"bib_path":"/root/test.bib","answer_path":"/root/answer.json","audit_path":"/root/citation_audit.json"}
JSON
```

Input schema:

- `bib_path` (required string): path to the input `.bib` file.
- `answer_path` (optional string, default `answer.json`): path to write `{"fake_citations":[...]}`.
- `audit_path` (optional string, default `citation_audit.json`): path for per-entry evidence and classifications.
- `timeout_sec` (optional number, default `15`): timeout for each web request.

The stdout summary gives the artifact paths, parsed-entry count, fake count, and review count. The audit contains source statuses and match candidates, so an executor can investigate entries marked `needs_review` with publisher-specific sources if task time permits. Do not add review-only titles to `answer.json` without independent verification.

## Validation

Before submitting, parse `answer_path` as JSON and confirm that it has exactly the `fake_citations` key, whose value is a list of strings. The script performs this validation before reporting success. Confirm titles are alphabetically sorted and have no remaining BibTeX braces or backslash commands. If the BibTeX file cannot be read or contains no parseable entries, treat that as an input failure rather than emitting an unsupported conclusion.
