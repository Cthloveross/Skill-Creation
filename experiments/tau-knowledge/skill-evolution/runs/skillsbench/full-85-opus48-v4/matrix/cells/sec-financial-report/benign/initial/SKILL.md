---
name: sec-13f-holdings-analysis
description: Analyze SEC Form 13F quarterly bulk EDGAR data (COVERPAGE/INFOTABLE/SUMMARYPAGE TSV tables) to answer institutional-holdings questions. Use when you are given quarterly 13F datasets (as folders or .zip archives of TSV files) and must fuzzy-match a filing manager by name, compute a fund's reported AUM, count the stocks it holds, rank quarter-over-quarter position changes by dollar value, or find the largest holders of a given security by CUSIP. Produces an answers.json file.
---

# SEC 13F Holdings Analysis

## When to use

The task gives two quarterly 13F EDGAR bulk datasets (Q2 and Q3 of a year). Each dataset
is a set of tab-separated tables that share `ACCESSION_NUMBER` as the join key:

- `COVERPAGE.tsv` – one row per filing: `FILINGMANAGER_NAME`, `ACCESSION_NUMBER`, `ISAMENDMENT`, ...
- `INFOTABLE.tsv` – one row per security position: `ACCESSION_NUMBER`, `NAMEOFISSUER`, `TITLEOFCLASS`, `CUSIP`, `VALUE`, `SSHPRNAMT`, `SSHPRNAMTTYPE`, `PUTCALL`, ...
- `SUMMARYPAGE.tsv`, `SUBMISSION.tsv`, etc. (supporting metadata, used only as cross-checks)

The public task supplies the data as `/root/13f-2025-q2.zip` and `/root/13f-2025-q3.zip`
(the opening text also refers to extracted folders `/root/2025-q2` and `/root/2025-q3`).
The Skill transparently extracts the zips if the folders are not already present, then
locates the TSV tables by walking the extracted tree (filenames matched case-insensitively).

## Key domain facts (from the frozen background)

- **AUM of a filing** = sum of the `VALUE` column over all `INFOTABLE` rows for the
  manager's accession number. For 2023-onward filings `VALUE` is already in **whole dollars**
  (do NOT multiply by 1000).
- **Accession numbers are quarter-specific.** Look the manager up independently in each
  quarter's `COVERPAGE`.
- **Name matching is fuzzy.** `FILINGMANAGER_NAME` is not standardized (case, `LLC` vs
  `L.L.C.`, trailing `INC`). Lowercase both query and candidates; prefer candidates that
  contain all query tokens, break ties by string similarity.
- **"Stocks held" is not a single SEC field.** You must declare an explicit policy for
  (a) which `TITLEOFCLASS`/security types count and (b) the counting unit (rows vs unique
  CUSIPs vs issuer positions). This Skill's default policy counts **unique CUSIPs of
  equity positions** (rows with blank `PUTCALL` and `SSHPRNAMTTYPE == 'SH'`), and also
  emits every alternative count to a diagnostics file so the executor can re-select.
- **Cross-quarter comparison** must aggregate `VALUE` by `CUSIP` within each quarter,
  then **outer-merge** on CUSIP with zero-fill for the missing quarter, so new buys and
  full exits are captured. Dollar change = `VALUE_Q3 - VALUE_Q2`.
- **Largest holders of a security**: find the security's CUSIP (search `NAMEOFISSUER`),
  filter `INFOTABLE` by that CUSIP, group by `ACCESSION_NUMBER`, sum `VALUE`, then join
  back to `COVERPAGE` for `FILINGMANAGER_NAME`.
- **Amendments / duplicate filings**: a manager may have several accession numbers in one
  quarter. This Skill prefers non-amendment (`ISAMENDMENT != 'Y'`) filings and, among
  those, the accession with the largest total reported value (the primary 13F).

## What the entrypoint answers

The public task asks four questions and wants `/root/answers.json` with schema:

```json
{
  "q1_answer": number,
  "q2_answer": number,
  "q3_answer": ["cusip1", "cusip2", "cusip3", "cusip4", "cusip5"],
  "q4_answer": ["fund1", "fund2", "fund3"]
}
```

- **q1** – Q3 AUM of Renaissance Technologies (sum of `VALUE` for its primary Q3 accession).
- **q2** – number of stocks held by Renaissance in Q3 (default policy: unique equity CUSIPs).
- **q3** – top-5 CUSIPs with the largest **positive** dollar change (Q3 − Q2) for Berkshire
  Hathaway, equity positions only, ranked descending by increase.
- **q4** – top-3 fund-manager names holding Palantir in Q3, by equity share value
  (de-duplicated by manager name so amendment copies do not double-count).

## How to run

The entrypoint reads an optional JSON config on stdin and writes `answers.json`
(plus a diagnostics file). With no config it uses the defaults below.

```bash
cd /app/environment/skills/current
echo '{}' | python3 scripts/run.py
```

Full config (all keys optional, shown with their defaults):

```json
{
  "q2_zip": "/root/13f-2025-q2.zip",
  "q3_zip": "/root/13f-2025-q3.zip",
  "q2_dir": "/root/2025-q2",
  "q3_dir": "/root/2025-q3",
  "output": "/root/answers.json",
  "diagnostics": "/root/answers_diagnostics.json",
  "renaissance_query": "renaissance technologies",
  "berkshire_query": "berkshire hathaway",
  "palantir_query": "palantir",
  "stock_count_mode": "unique_cusip_equity"
}
```

`stock_count_mode` accepts: `unique_cusip_equity` (default), `unique_cusip_all`,
`rows_equity`, `rows_all`. The diagnostics file always reports **all** of these counts
for the chosen Renaissance accession, the fuzzy match that was selected (name + score +
all candidate accessions + their totals), the CUSIP(s) found for Palantir, and the full
ranked change list used for q3/q4 — so if a verifier rejects a value, the executor can
inspect the diagnostics and either pick a different `stock_count_mode` or adjust a query
without rewriting logic.

## stdout schema

`run.py` prints a JSON object to stdout: `{"answers": {...}, "diagnostics_path": "...",
"output_path": "..."}`. A nonzero exit or an `error` key means a required table or match
was not found — inspect the message, confirm the zips extracted, and re-run.

## Validation the executor should perform

1. Run the command above; confirm it exits 0 and `/root/answers.json` exists.
2. `cat /root/answers.json` and check: `q1_answer` is a plausible large dollar figure
   (billions, whole dollars, not thousands), `q2_answer` is a positive integer,
   `q3_answer` is exactly 5 nine-character CUSIP strings, `q4_answer` is exactly 3
   non-empty manager-name strings.
3. `cat /root/answers_diagnostics.json` to confirm the fuzzy matches resolved to the
   expected entities (names containing "RENAISSANCE", "BERKSHIRE", and a Palantir CUSIP),
   and that the primary accession chosen is a non-amendment filing.
4. Because the entrypoint regenerates `answers.json` from the raw data on each run, prefer
   re-running it over hand-editing the JSON. If a specific answer is disputed by verifier
   feedback, change the relevant config knob (e.g. `stock_count_mode`) or the query term,
   not the computed arithmetic.

## Failure handling

- Missing zip and missing extracted folder → the script reports which path failed.
- No fuzzy match above the fallback (no candidate shares a query token) → reports the
  best candidate so the executor can refine the query.
- Empty `VALUE` cells are treated as 0; CUSIPs are upper-cased and stripped.
- Unsupported `stock_count_mode` falls back to the default and notes it in diagnostics.
