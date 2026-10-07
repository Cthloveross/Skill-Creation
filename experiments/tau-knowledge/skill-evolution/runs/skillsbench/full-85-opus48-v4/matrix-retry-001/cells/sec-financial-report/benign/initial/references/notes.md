# 13F methodology notes

- `ACCESSION_NUMBER` joins COVERPAGE, INFOTABLE, SUMMARYPAGE. It changes every
  quarter; always re-look-up per quarter's COVERPAGE.
- 2023+ `INFOTABLE.VALUE` is in whole dollars. Do NOT multiply by 1000.
- AUM from a 13F = sum of VALUE over all rows for the accession (reported long
  equity book only; excludes shorts, bonds, cash, swaps).
- Fuzzy name match: lowercase + collapse whitespace, difflib ratio, +1.0 boost
  when all query tokens are substrings of the candidate; prefer ISAMENDMENT=N.

## Stock-count policy (q2) is intentionally explicit

"stocks held" is not a native SEC field. The entrypoint reports four variants:
`equity_unique_cusip` (default), `equity_rows`, `all_unique_cusip`, `all_rows`,
plus SUMMARYPAGE.TABLEENTRYTOTAL as a cross-check. Equity = PUTCALL blank and
SSHPRNAMTTYPE != 'PRN' (share positions, excluding options and
principal/convertible). If grading contradicts the default, re-run with another
`stock_count_policy`; do not hand-edit the number.

## Quarter comparison (q3)

Aggregate equity VALUE by CUSIP per quarter, outer-merge with zero-fill, so new
buys (absent in Q2) and complete exits (absent in Q3) are captured. Rank by
`VALUE_Q3 - VALUE_Q2` descending; the top positive changes are the biggest
increases. Report CUSIPs.

## Top holders of a security (q4)

Identify the security's rows by issuer-name substring in Q3 INFOTABLE, collect
its CUSIP(s), aggregate VALUE per accession, collapse duplicate manager names
(keep the highest-value filing to avoid double-counting amendments), join
COVERPAGE names, take the top N by value.
