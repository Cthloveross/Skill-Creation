---
name: verify-bibtex-citations
description: Audit a runtime-supplied BibTeX bibliography for fabricated or mismatched academic citations and write a sorted JSON list of cleaned fake-paper titles. Use when DOI registry checks and bibliographic-index corroboration are available.
---

# Verify BibTeX citations

Use this Skill to assess the actual bibliography supplied at runtime. A plausible title, DOI-shaped string, or a failed search alone is not evidence that a citation is real or fake.

## Entrypoint

Run `scripts/audit_bibliography.py` with one JSON object on stdin:

```json
{"bib_path":"/root/test.bib","output_path":"/root/answer.json","audit_path":"/root/citation-audit.json"}
```

Input fields:

- `bib_path` (required string): source `.bib` file.
- `output_path` (required string): required answer destination.
- `audit_path` (optional string): evidence report destination; defaults beside `output_path`.
- `timeout_seconds` (optional number, default `15`): per-request HTTP timeout.
- `manual_overrides` (optional object): citation-key mappings to `fake`, `real`, or `unverified`, only after authoritative manual follow-up.

The entrypoint reads JSON from stdin and emits one JSON summary to stdout. It writes `output_path` as exactly:

```json
{"fake_citations":["cleaned title", "..."]}
```

It also writes the audit report, which is for review and must not replace the required answer file.

## Method

1. Invoke the entrypoint against the supplied file. It parses balanced BibTeX fields, keeps citation keys for auditability, and removes common brace and LaTeX title markup before lookup and output.
2. For each DOI, query Crossref's exact DOI endpoint. If it is absent there, query DataCite. Record resolution evidence and compare normalized title, author surnames, venue, year, volume, and pages where both sides provide a value.
3. A resolving DOI with a substantially matching title is strong positive evidence. A DOI absent from both registries is strong fabrication evidence; a DOI resolving to a radically different title is a mismatched/fabricated citation. Transcription-level metadata differences are recorded for review rather than automatically called fake.
4. For records not confirmed by DOI, query Crossref title search, Semantic Scholar, and DBLP. An exact normalized title match is positive corroboration. The audit never calls an item fake merely because an index or network request fails.
5. For a no-DOI record, the script may classify it as fake only when a healthy Crossref search returns several *different* candidate works and none agrees with the claimed authors or venue. This is a positive metadata contradiction, not a bare absence result. Other uncertain records remain `unverified`.
6. Review `citation-audit.json` for `unverified`, `mismatched_doi`, errors, and any ambiguous metadata. For an item that needs a decision beyond the automated evidence, verify the exact title/authors in an authoritative publisher, venue, library, or index source, then rerun with a documented `manual_overrides` decision. Do not include uncertain items in the answer.
7. Submit only `answer.json` to the task requester; do not add keys, explanations, or audit details to that file.

Example:

```sh
python3 /app/environment/skills/current/scripts/audit_bibliography.py <<'EOF2'
{"bib_path":"/root/test.bib","output_path":"/root/answer.json","audit_path":"/root/citation-audit.json"}
EOF2
```

## Validation

The entrypoint validates that the answer has only `fake_citations`, contains a sorted unique list of strings, and has no raw braces or backslashes in output titles. Before submission, parse the output JSON and inspect the audit to ensure no item was classified as fake solely from an HTTP error or lack of search results.
