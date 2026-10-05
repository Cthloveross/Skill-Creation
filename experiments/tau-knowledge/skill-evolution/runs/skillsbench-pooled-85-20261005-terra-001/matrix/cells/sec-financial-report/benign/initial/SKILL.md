---
name: sec-13f-quarterly-holdings-analysis
description: Analyze SEC Form 13F quarterly bulk TSV archives to calculate a named manager's reported 13F value and holdings count, compare a manager's CUSIP positions across quarters, and rank managers holding a named issuer. Use for tasks with COVERPAGE.tsv and INFOTABLE.tsv data, especially zipped EDGAR quarterly downloads.
---

# SEC 13F Quarterly Holdings Analysis

Use `scripts/analyze_13f.py` to produce the required `/root/answers.json` artifact from the supplied 2025 Q2 and Q3 EDGAR bulk-data archives. The script uses only Python's standard library and streams TSVs directly from ZIP files, avoiding extraction of the large INFOTABLE files.

## Method

1. Discover `COVERPAGE.tsv` and `INFOTABLE.tsv` by basename in each supplied directory or ZIP archive.
2. Fuzzy-rank `FILINGMANAGER_NAME` values for the requested Renaissance and Berkshire queries. A non-amendment filing is preferred when otherwise equivalent.
3. Sum Q3 Renaissance `VALUE` rows for reported 13F value. For 2025, `VALUE` is treated as dollars.
4. Count Renaissance Q3 holdings under an explicit, configurable security policy. The default counts distinct CUSIPs for share-based, non-option holdings; it excludes `PUTCALL` rows and `SSHPRNAMTTYPE=PRN` rows.
5. Independently resolve Berkshire's Q2 and Q3 accessions, aggregate eligible positions by CUSIP, outer-join via the union of CUSIPs, and rank positive Q3-minus-Q2 dollar changes.
6. Detect Palantir's CUSIP from `NAMEOFISSUER`, aggregate its Q3 `VALUE` by filing accession, join to manager names from COVERPAGE, and rank the manager totals.

## Run

The task paths are defaults, so in the supplied environment run:

```bash
python3 scripts/analyze_13f.py <<'JSON'
{}
JSON
```

The script writes `/root/answers.json` and emits that same JSON object on stdout.

Optional JSON input schema:

```json
{
  "q2_source": "/root/13f-2025-q2.zip",
  "q3_source": "/root/13f-2025-q3.zip",
  "output_path": "/root/answers.json",
  "stock_policy": "share_non_option_unique_cusip"
}
```

Each source may instead be an extracted quarterly directory. Supported `stock_policy` values are:

- `share_non_option_unique_cusip` (default): distinct CUSIPs with `SSHPRNAMTTYPE=SH` and blank `PUTCALL`.
- `common_share_unique_cusip`: the default rule plus a common-share-like `TITLEOFCLASS` label.
- `all_unique_cusip`: all distinct nonblank CUSIPs in the selected filing.
- `row_count`: count eligible share/non-option INFOTABLE rows rather than CUSIPs.

## Output and validation

The emitted object and written artifact have this exact schema:

```json
{
  "q1_answer": 0,
  "q2_answer": 0,
  "q3_answer": ["CUSIP", "CUSIP", "CUSIP", "CUSIP", "CUSIP"],
  "q4_answer": ["Manager", "Manager", "Manager"]
}
```

The script validates that totals are numeric, the increase list contains exactly five nonblank CUSIPs, and the Palantir list contains exactly three nonblank manager names. It fails rather than silently emitting a partial answer if a table, manager match, security match, or required rank is unavailable. Review a non-default stock policy against the actual `TITLEOFCLASS`, `PUTCALL`, and `SSHPRNAMTTYPE` labels when the task defines “stocks” differently.
