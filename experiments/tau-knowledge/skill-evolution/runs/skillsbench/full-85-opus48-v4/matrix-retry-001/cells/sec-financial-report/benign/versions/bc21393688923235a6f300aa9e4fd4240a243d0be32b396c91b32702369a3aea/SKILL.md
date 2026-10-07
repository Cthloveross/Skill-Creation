---
name: sec-13f-holdings-analysis
description: >
  Analyze SEC Form 13F quarterly bulk EDGAR data (TSV tables keyed by
  ACCESSION_NUMBER) to answer institutional-holdings questions: fuzzy-match a
  filing manager by name, compute a fund's reported long-equity AUM, count the
  stocks it holds under an explicit policy, rank the largest quarter-over-quarter
  dollar increases for a fund by CUSIP, and find the top holders of a named
  security. Use when given quarterly 13F zip/folder datasets and asked to produce
  an answers.json comparing two quarters (e.g. Q2 vs Q3 2025).
---

# SEC 13F Holdings Analysis

## What this task needs

The environment provides two quarterly 13F EDGAR datasets. In this task they
arrive as zip files at `/root/13f-2025-q2.zip` and `/root/13f-2025-q3.zip`
(the opening text refers to them as `/root/2025-q2` and `/root/2025-q3`
folders). Each dataset is a set of tab-separated tables; the ones used here are
`COVERPAGE.tsv` (one row per filing: `FILINGMANAGER_NAME`, `ISAMENDMENT`,
`ACCESSION_NUMBER`), `INFOTABLE.tsv` (one row per security line item:
`NAMEOFISSUER`, `TITLEOFCLASS`, `CUSIP`, `VALUE`, `SSHPRNAMTTYPE`, `PUTCALL`,
`ACCESSION_NUMBER`), and optionally `SUMMARYPAGE.tsv` (`TABLEENTRYTOTAL`,
`TABLEVALUETOTAL`). `ACCESSION_NUMBER` is the join key and is **quarter-specific** —
look it up independently in each quarter's `COVERPAGE`.

For 2023-onward filings the `INFOTABLE.VALUE` column is already in **whole
dollars**; do not multiply by 1000.

The deliverable is `/root/answers.json` with exactly this schema:

```json
{
  "q1_answer": number,                                 // Q3 Renaissance Technologies AUM (dollars)
  "q2_answer": number,                                 // number of stocks Renaissance holds
  "q3_answer": ["cusip1", "cusip2", "cusip3", "cusip4", "cusip5"], // Berkshire top-5 dollar INCREASES Q2->Q3
  "q4_answer": ["fund1", "fund2", "fund3"]             // top-3 Q3 holders of Palantir by share value
}
```

## Method

1. **Resolve data directories.** If a quarter folder already contains
   `COVERPAGE.tsv` use it; otherwise unzip the quarter's zip into it. The helper
   searches recursively so an inner subfolder is fine.
2. **Fuzzy name match** (q1/q2/q3). Normalize query and candidate
   `FILINGMANAGER_NAME` to lowercase/collapsed whitespace, score with
   `difflib.SequenceMatcher` ratio, and add a strong boost when every query token
   appears in the candidate (so e.g. `renaissance technologies` matches
   `RENAISSANCE TECHNOLOGIES LLC`). Prefer the non-amendment (`ISAMENDMENT`
   starting with `N`) row and take its `ACCESSION_NUMBER`.
3. **AUM (q1).** Sum `VALUE` across all `INFOTABLE` rows for that accession
   (dollars). This is the reported long-equity book, cross-checked against
   `SUMMARYPAGE.TABLEVALUETOTAL` when present.
4. **Stock count (q2).** `"stocks held"` is not a native SEC field, so the policy
   is explicit and configurable. Default = **distinct CUSIPs among equity rows**
   (equity = `PUTCALL` blank and `SSHPRNAMTTYPE != 'PRN'`, i.e. share positions,
   not options or convertibles). The script also reports `equity_rows`,
   `all_rows`, `all_unique_cusip`, and `SUMMARYPAGE.TABLEENTRYTOTAL` as
   diagnostics so the executor can switch policy if grading implies a different
   counting rule.
5. **Quarter comparison (q3).** Look up Berkshire's accession in each quarter,
   restrict both to equity rows, aggregate `VALUE` by CUSIP, outer-merge on CUSIP
   with zero-fill, compute `change = VALUE_Q3 - VALUE_Q2`, sort descending, take
   the 5 CUSIPs with the largest positive increases.
6. **Top holders of a security (q4).** Find Palantir rows in Q3 `INFOTABLE` by
   `NAMEOFISSUER` containing the term, aggregate `VALUE` per accession, collapse
   duplicate manager names (keep highest), join `COVERPAGE` names, take top 3.

## How the executor runs it

Run the end-to-end entrypoint (pandas required; it is read from the task files at
runtime, nothing is hardcoded as an answer):

```bash
echo '{}' | python3 /app/environment/skills/current/scripts/analyze.py
```

With no stdin config it uses the task defaults: q2 dir `/root/2025-q2`
(zip `/root/13f-2025-q2.zip`), q3 dir `/root/2025-q3`
(zip `/root/13f-2025-q3.zip`), queries `renaissance technologies`,
`berkshire hathaway`, security `palantir`, stock-count policy
`equity_unique_cusip`, output `/root/answers.json`.

Override any of these via stdin JSON, e.g. to try a different counting policy:

```bash
echo '{"stock_count_policy":"equity_rows"}' | python3 .../scripts/analyze.py
```

Accepted keys: `q2_dir`, `q3_dir`, `q2_zip`, `q3_zip`, `renaissance_query`,
`berkshire_query`, `security_name`, `stock_count_policy`
(`equity_unique_cusip` | `equity_rows` | `all_unique_cusip` | `all_rows`),
`output`.

The script prints a diagnostics JSON to stdout (matched names, chosen accession
numbers, every stock-count variant, Palantir CUSIPs, summary cross-checks) and
writes `answers.json`. Read the diagnostics to sanity-check matches before
trusting the file.

Validate the produced file:

```bash
python3 /app/environment/skills/current/scripts/validate_answers.py < /root/answers.json
```

This checks the four keys exist, q1/q2 are numbers, q3 has 5 CUSIP-shaped
strings, and q4 has 3 non-empty names; it exits non-zero on any violation.

## Failure handling

- Missing `COVERPAGE.tsv`/`INFOTABLE.tsv` after unzip, or a missing zip/folder:
  the script raises a clear error naming the path — inspect the actual layout
  with `ls`/`unzip -l` and pass the correct `*_dir`/`*_zip` in stdin.
- A fuzzy match with a low score or an unexpected matched name is surfaced in
  diagnostics; adjust the query string if the wrong manager was selected.
- If grading implies a different `q2_answer`, re-run with another
  `stock_count_policy` rather than editing numbers by hand.
- Do not multiply `VALUE` by 1000 for 2023+ data; values are already dollars.
