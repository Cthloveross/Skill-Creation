---
name: stock-sector-force-bubbles
summary: Build an offline-served D3 v6 single-page stock dashboard from a stock-description CSV and related input-data directory.
description: Use when a task requires a local D3 v6 bubble chart clustered by a categorical sector field, an adjacent stock table, market-cap formatting, tooltip suppression for incomplete records, and linked selection. The builder discovers common CSV header variants at browser runtime, copies all supplied data, and downloads the required local D3 v6 asset.
---

# Stock sector force-bubble dashboard

Run `scripts/build_stock_bubbles.py` with JSON on stdin. It creates the requested application files below `output_dir`:

- `index.html`
- `css/style.css`
- `js/d3.v6.min.js`
- `js/visualization.js`
- `data/` (a recursive copy of `source_dir`, including the description CSV and any price-history files)

## Input schema

```json
{
  "source_dir": "/root/data",
  "output_dir": "/root/output",
  "d3_url": "https://d3js.org/d3.v6.min.js"
}
```

`source_dir` must contain `stock-descriptions.csv`. `d3_url` is optional and is useful when the normal D3 v6 distribution URL is mirrored by the execution environment. The script uses only the standard Python library, emits one JSON result object to stdout, and returns a nonzero status after emitting `{ "ok": false, "error": ... }` when an input, copy, or asset-download prerequisite fails.

Example executor call:

```bash
python3 scripts/build_stock_bubbles.py <<'JSON'
{"source_dir":"/root/data","output_dir":"/root/output"}
JSON
```

Serve `output_dir` over a local HTTP server when opening the generated page. The application intentionally loads its copied CSV through D3, which browsers do not reliably permit from a `file://` URL.

## Implementation notes

The generated app loads local D3 before its visualization script and uses `d3.csv` with an explicit numeric parser. It recognizes case/punctuation variants of ticker, company name, sector, market cap, country, and website fields. Records with missing market capitalization receive a common radius; a record only receives a hover tooltip when market cap, country, and website are all present.

The chart uses a square-root radius scale, per-sector `forceX`/`forceY` targets, `forceCenter`, and collision radii derived from the exact rendered radii. Bubble labels are children of an interaction group and have `pointer-events: none`, so labels cannot create hover dead zones. The HTML legend is built from every sector found in the CSV. A single selected ticker drives both bubble and table-row highlighting.

## Validation

The builder validates that the input CSV exists, verifies the downloaded D3 file is nonempty and identifies a v6 distribution, confirms the copied CSV exists, and checks all declared app files before reporting success. After serving the output, verify that the status message reports the loaded row count, the legend covers the visible sector categories, no table cell displays `NaN` or `undefined`, and selecting either a table row or bubble highlights its counterpart.
