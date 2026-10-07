---
name: sec-13f-quarterly-holdings-analysis
description: Produce a required answers.json from SEC Form 13F quarterly bulk TSV data. Use for Q2/Q3 manager-value, reported-entry, CUSIP-change, and issuer-holder ranking questions with COVERPAGE.tsv and INFOTABLE.tsv inputs in directories or ZIP archives.
---

# SEC 13F Quarterly Holdings Analysis

Run `scripts/analyze_13f.py` to create the requested `/root/answers.json`. It reads the supplied EDGAR files at execution time, uses only the Python standard library, and streams large TSV files without extracting ZIP archives.

## Calculation rules

The script implements the requested reporting conventions:

1. It fuzzy-matches the requested manager query in each quarter's `COVERPAGE.tsv`, preferring a containing normalized name and then a non-amendment filing.
2. It computes the Renaissance Q3 reported 13F value by summing every matching `INFOTABLE.tsv` `VALUE` row. 2025 `VALUE` is interpreted as dollars.
3. It reports Renaissance's number of reported Q3 INFOTABLE entries. This is a filing line-entry count, not a count of unique CUSIPs; a fund can report the same security on multiple entries.
4. It independently resolves Berkshire Hathaway's Q2 and Q3 filings, aggregates every holding by the source CUSIP string within each filing, uses zero for absent-quarter positions, and returns the five largest positive Q3-minus-Q2 increases.
5. It identifies the Palantir Technologies equity CUSIP from issuer identity rather than a bare `palantir` substring. Separately reported put/call rows are excluded. The resolver requires a syntactically valid CUSIP and selects the repeatedly reported canonical candidate, then aggregates its value per filing accession and joins accession numbers to the Q3 COVERPAGE manager names.

CUSIPs for the Berkshire answer are retained exactly as represented in the relevant TSV. Palantir CUSIPs are compared case-insensitively so casing variants are correctly combined.

## Run

The defaults support the supplied ZIP inputs:

```bash
python3 scripts/analyze_13f.py <<'JSON'
{}
JSON
```

The script emits the answer object on stdout and writes it to `/root/answers.json`.

Optional stdin is one JSON object:

```json
{
  "q2_source": "/root/13f-2025-q2.zip",
  "q3_source": "/root/13f-2025-q3.zip",
  "output_path": "/root/answers.json"
}
```

A source can be either a ZIP archive or an extracted quarterly directory containing the TSV files.

## Output validation

The generated artifact has exactly this JSON shape:

```json
{
  "q1_answer": 0,
  "q2_answer": 0,
  "q3_answer": ["CUSIP", "CUSIP", "CUSIP", "CUSIP", "CUSIP"],
  "q4_answer": ["Manager", "Manager", "Manager"]
}
```

The program fails rather than writing a partial artifact if an input table is absent, a manager cannot be resolved, a required filing has no holdings, Palantir cannot be resolved unambiguously, or fewer than five increases or three holders are available. Inspect any such failure against the supplied source schema rather than substituting identifiers or answer values.
