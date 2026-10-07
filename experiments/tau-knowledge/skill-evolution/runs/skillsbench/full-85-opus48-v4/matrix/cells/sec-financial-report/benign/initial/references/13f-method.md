# 13F analysis method (quick reference)

Join key across all tables: `ACCESSION_NUMBER`. Accession numbers are unique per
quarter, so look a manager up separately in each quarter's `COVERPAGE`.

## AUM
Sum `INFOTABLE.VALUE` over all rows for the manager's accession. 2023+ filings
report `VALUE` in whole dollars (no x1000). This is the reported long-equity book,
not the fund's true total AUM.

## Name matching
`FILINGMANAGER_NAME` is free text. Normalize to lowercase, strip punctuation.
Prefer candidates containing every query token; break ties by string similarity.
Among a manager's filings prefer `ISAMENDMENT != 'Y'`, then the accession with the
largest total value (the primary 13F).

## Counting "stocks held" (requires an explicit, declared policy)
There is no single SEC field. Decide BOTH:
  1. Security universe: this Skill's equity policy = blank `PUTCALL` AND
     `SSHPRNAMTTYPE == 'SH'` (excludes options and principal-amount/convertible rows).
  2. Counting unit: rows vs unique CUSIPs vs issuer positions.
Default = unique equity CUSIPs. The entrypoint also emits every alternative count
to the diagnostics file so the unit can be re-selected if feedback requires it.
`TITLEOFCLASS` is inconsistent free text; inspect the labels actually present in a
filing instead of importing a fixed whitelist from an unrelated benchmark.

## Quarter-over-quarter change
Aggregate `VALUE` by `CUSIP` within each quarter (a filing can list the same CUSIP
in multiple voting-authority rows), outer-merge on CUSIP, zero-fill the missing
quarter, then change = Q3 - Q2. Rank descending for largest increases; a security
present only in Q3 is a new buy (change = full Q3 value), present only in Q2 is a
full exit.

## Largest holders of a security
Find the security's CUSIP by searching `NAMEOFISSUER`. Filter `INFOTABLE` by that
CUSIP, group by `ACCESSION_NUMBER`, sum `VALUE`, join back to `COVERPAGE` for
`FILINGMANAGER_NAME`, sort descending. De-duplicate by manager name so amendment
copies of the same filing do not double-count a holder.
