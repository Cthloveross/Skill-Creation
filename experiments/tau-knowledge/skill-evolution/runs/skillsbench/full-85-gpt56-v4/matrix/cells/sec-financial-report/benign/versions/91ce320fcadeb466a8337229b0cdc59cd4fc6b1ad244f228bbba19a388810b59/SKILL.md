---
name: sec-13f-quarterly-holdings-analysis
description: Produce the required answers.json for a 13F quarterly-holdings task involving manager AUM, holdings counts, cross-quarter investment increases, and largest holders of a named issuer. Use when quarterly EDGAR bulk TSV data is supplied as directories or ZIP archives.
---

# SEC 13F quarterly holdings analysis

Use `scripts/analyze_13f.py` to analyze the supplied Q2 and Q3 bulk-data sets and create the requested JSON response. The script uses only the standard library and can read either extracted data folders or ZIP archives, so it avoids manually extracting very large `INFOTABLE.tsv` files.

## Method and assumptions

1. It fuzzy-matches the requested manager names against `COVERPAGE.tsv`, then uses the selected quarter-specific `ACCESSION_NUMBER` to filter `INFOTABLE.tsv`.
2. Q3 Renaissance AUM is the sum of every `VALUE` line for its selected accession. For 2025, `VALUE` is treated as dollars, not thousands.
3. The Renaissance stock count defaults to **unique CUSIPs** among share-based, non-option positions (`SSHPRNAMTTYPE=SH` and blank `PUTCALL`). This is an explicitly stated security-level counting unit rather than a row count. Set `stock_count_unit` to `rows` if a task expressly defines holdings as table entries.
4. For Berkshire's comparison, it filters both quarters to that same share-based, non-option universe, sums `VALUE` by CUSIP in each quarter, outer-joins logically by using zero for absent values, and ranks strictly positive Q3-minus-Q2 dollar changes.
5. For the issuer-holder question, it finds the best issuer-name match in Q3 `INFOTABLE.tsv`, aggregates its values by filing accession, joins those accessions to Q3 `COVERPAGE.tsv`, and sorts descending by dollar `VALUE`.

The word “stocks” is not a standardized 13F field. If the task supplies a more specific definition (for example, only `TITLEOFCLASS=COM`), adapt the share-universe predicate consistently for both count and comparison; do not silently mix security definitions across quarters.

## Run

From the supplied working directory, run:

```sh
python3 /app/environment/skills/current/scripts/analyze_13f.py <<'JSON'
{
  "q2_path": "/root/2025-q2",
  "q3_path": "/root/2025-q3",
  "output_path": "/root/answers.json"
}
JSON
```

If the stated folders are absent and the environment supplies archives instead, pass their paths directly, for example `/root/13f-2025-q2.zip` and `/root/13f-2025-q3.zip`. With no input, the script also searches these common folder/archive locations under `/root`.

### JSON stdin schema

All fields are optional except that usable Q2 and Q3 sources must be discoverable.

```json
{
  "q2_path": "directory or .zip for Q2",
  "q3_path": "directory or .zip for Q3",
  "output_path": "/root/answers.json",
  "renaissance_query": "renaissance technologies",
  "berkshire_query": "berkshire hathaway",
  "palantir_query": "palantir",
  "stock_count_unit": "unique_cusips"
}
```

`stock_count_unit` may be `unique_cusips` (default) or `rows`. The script writes the exact required response schema to `output_path` and prints a JSON diagnostic object to stdout containing selected manager names, accessions, and the output.

## Validation

Before treating the result as complete, verify that `/root/answers.json` exists, parses as JSON, has numeric `q1_answer` and `q2_answer`, and each of `q3_answer` and `q4_answer` has exactly five and three string entries respectively. The script performs these checks itself and fails rather than emitting a partial answer if a table, manager match, issuer match, or enough ranked records cannot be found.
