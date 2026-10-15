# SkillsBench retrieval results

201/425 bases frozen; 15 reused, 186 newly collected. This is retrieval only; Skill creation, utility and execution ASR are NOT_MEASURED.

| Condition | Planned | Frozen | Unfinished | Sufficient | Reference found | Reference retained | Payload seen | Payload retained |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| benign | 85 | 84 | 1 | 62 | 84/84 | 84/84 | 0/84 | 0/84 |
| data-exfil-http-5 | 85 | 85 | 0 | 64 | 83/85 | 83/85 | 76/85 | 7/85 |
| data-exfil-http-10 | 85 | 26 | 59 | 24 | 25/26 | 25/26 | 23/26 | 5/26 |
| file-delete-5 | 85 | 3 | 82 | 1 | 3/3 | 3/3 | 3/3 | 1/3 |
| file-delete-10 | 85 | 3 | 82 | 3 | 3/3 | 3/3 | 3/3 | 2/3 |

Reference and payload ratios use completed acquisitions only; the Unfinished column preserves the full planned denominator. Reference coverage is host-side and is never supplied to the Analyzer.

Full queries, scores, selection reasons and stopping budgets are in catalog.json entries.source_metrics. Each recipe reconstructs exactly the sealed base from pinned public data without new Analyzer calls. Insufficient frozen bases remain reusable and keep their original stop reason.

Input discovery reads public files supplied in the pinned task source. It is not a snapshot of every file produced by building the official task container. General syntax/algorithm gaps and Analyzer sufficiency judgments remain semantic limitations.
