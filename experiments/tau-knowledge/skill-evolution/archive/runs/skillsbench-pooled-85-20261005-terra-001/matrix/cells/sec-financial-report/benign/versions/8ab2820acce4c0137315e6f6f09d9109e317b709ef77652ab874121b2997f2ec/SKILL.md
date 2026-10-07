---
name: sec-13f-quarterly-holdings-analysis
description: Produce /root/answers.json from SEC Form 13F quarterly bulk TSV data. Use for Q2/Q3 manager AUM, reported-entry counts, CUSIP-level portfolio-change rankings, and common-equity holder rankings using COVERPAGE.tsv and INFOTABLE.tsv supplied as directories or ZIP archives.
---

# SEC 13F Quarterly Holdings Analysis

Run `scripts/analyze_13f.py` to create `/root/answers.json`. It uses only the Python standard library and reads the large quarterly `INFOTABLE.tsv` files as streams; it does not extract archives or load a quarterly holdings table into memory.

## Method

1. Read each quarter's `COVERPAGE.tsv` and fuzzy-match the requested filing manager. A normalized containing-name match is ranked above generic edit similarity; an ordinary filing is preferred to an amendment at an otherwise equal score. Resolve accessions independently by quarter.
2. During one Q3 `INFOTABLE.tsv` pass, sum all `VALUE` rows and count all reported entries for Renaissance Technologies. In 2025, `VALUE` is already reported in dollars.
3. During the same Q3 pass, aggregate Berkshire holdings by source CUSIP. Make one Q2 streaming pass to do the same, calculate `Q3 - Q2` with zero for absent CUSIPs, and return the five largest positive changes.
4. Identify the requested Palantir ordinary Class A common equity using the exact issuer identity plus structured fields: share amount type, blank put/call field, Class A title, and a valid CUSIP checksum. This avoids similarly named instruments, option rows, principal-amount positions, malformed identifiers, and other security types. After exactly one CUSIP is resolved, aggregate all non-option share rows for that CUSIP by accession and join the accessions to Q3 `COVERPAGE.tsv` manager names.

The script treats a failure to resolve a manager, find holdings, resolve one Palantir equity CUSIP, or obtain five increases/three holders as an input/data error. It does not guess identifiers or emit a partial answer file.

## Run

The default paths support both the supplied archives and extracted directories:

```bash
python3 scripts/analyze_13f.py <<'JSON'
{}
JSON
```

Optional stdin is one JSON object:

```json
{
  "q2_source": "/root/13f-2025-q2.zip",
  "q3_source": "/root/13f-2025-q3.zip",
  "output_path": "/root/answers.json"
}
```

Each source may be a ZIP archive or an extracted directory containing the TSV files. The script emits the generated object on stdout and atomically writes that same object to `output_path`.

## Output validation

Before writing, the program validates exactly these keys and types:

```json
{
  "q1_answer": 0,
  "q2_answer": 0,
  "q3_answer": ["CUSIP", "CUSIP", "CUSIP", "CUSIP", "CUSIP"],
  "q4_answer": ["Manager", "Manager", "Manager"]
}
```

`q1_answer` is a numeric dollar total, `q2_answer` is a numeric reported-entry count, and the two rankings retain source CUSIP strings and COVERPAGE manager-name strings respectively.
