---
name: sec-13f-quarterly-holdings-analysis
description: Create answers.json for SEC Form 13F quarterly bulk TSV data. Use for Q2/Q3 manager AUM, entry count, CUSIP-level portfolio-change, and ordinary-common-stock holder ranking tasks using COVERPAGE.tsv and INFOTABLE.tsv from directories or ZIP archives.
---

# SEC 13F Quarterly Holdings Analysis

Run `scripts/analyze_13f.py` to create `/root/answers.json`. The script reads supplied EDGAR data at execution time, uses only the Python standard library, and streams large TSV files without extracting ZIP archives.

## Method

1. Fuzzy-match each requested manager in that quarter's `COVERPAGE.tsv`. A normalized containing name is preferred over generic edit similarity, and a non-amendment filing wins an otherwise equivalent match.
2. Sum all Q3 Renaissance `INFOTABLE.tsv` `VALUE` rows to compute reported 13F value. For 2025, `VALUE` is already in dollars. Count its rows as the requested reported-entry count.
3. Resolve Berkshire separately for Q2 and Q3. Aggregate every filing's holdings by source CUSIP, zero-fill missing quarter values, calculate Q3 minus Q2, and rank positive increases.
4. Resolve Palantir from its issuer identity **and structured security fields**. The selected row must be a non-option, share-based (`SSHPRNAMTTYPE=SH`) Palantir Technologies Class A/common-equity row with a valid CUSIP checksum. This rejects similarly named instruments, principal-amount instruments, option positions, and malformed records. The resolver requires exactly one resulting canonical CUSIP rather than guessing between candidates. Aggregate that CUSIP's `VALUE` by filing accession, then join `COVERPAGE.tsv` manager names and rank descending.

CUSIPs used for Berkshire's answer remain exactly as represented in its source TSV. Palantir matching canonicalizes case and whitespace only for identifying the same security.

## Run

The defaults support either supplied ZIP files or their extracted directories:

```bash
python3 scripts/analyze_13f.py <<'JSON'
{}
JSON
```

The script writes `/root/answers.json` and emits the same JSON object on stdout. Optional stdin is one JSON object:

```json
{
  "q2_source": "/root/13f-2025-q2.zip",
  "q3_source": "/root/13f-2025-q3.zip",
  "output_path": "/root/answers.json"
}
```

Each source may be a ZIP archive or an extracted directory containing the TSV files.

## Output validation

The resulting artifact has exactly this shape:

```json
{
  "q1_answer": 0,
  "q2_answer": 0,
  "q3_answer": ["CUSIP", "CUSIP", "CUSIP", "CUSIP", "CUSIP"],
  "q4_answer": ["Manager", "Manager", "Manager"]
}
```

The program fails without writing a partial artifact when an input table is missing, a manager cannot be resolved, a selected filing has no holdings, the structured Palantir resolver is ambiguous, or fewer than five increases or three holders exist. Inspect the supplied source schema and data in that event; do not substitute identifiers or result values.
