---
name: d3-stock-cluster-dashboard
description: Build a self-contained D3.js v6 single-page stock dashboard from a stock-description CSV and a directory of individual stock CSV files. Use when a task requires sector-clustered, collision-free market-cap bubbles, a linked stock table, conditional company-only tooltips, and a local copy of D3 and source data.
---

# D3 Stock Cluster Dashboard

Use `scripts/build_stock_dashboard.py` to create the requested app. The builder reads supplied data at execution time and never embeds stock identities or financial values.

## Runtime interface

The script receives one JSON object on stdin and emits one JSON object on stdout.

```json
{
  "source_data": "/root/data",
  "output_dir": "/root/output",
  "d3_source": "/optional/local/d3.v6.min.js",
  "d3_url": "https://d3js.org/d3.v6.min.js"
}
```

- `source_data` must contain `stock-descriptions.csv` and `indiv-stock/`.
- `output_dir` is created if needed.
- `d3_source` optionally provides a local D3 v6 distribution. If absent, the builder downloads `d3_url` and saves it locally as `js/d3.v6.min.js`.

Example:

```sh
python3 scripts/build_stock_dashboard.py <<'JSON'
{"source_data":"/root/data","output_dir":"/root/output"}
JSON
```

A success response lists generated paths and the number of copied history files. Missing prerequisites, failed copy operations, and failed D3 acquisition emit `{ "ok": false, "error": "..." }` and exit nonzero.

## Generated behavior

`index.html` loads local D3 v6 before `visualization.js`, and the visualization loads `data/stock-descriptions.csv`. Serve the output directory through HTTP because browsers normally block CSV fetching from `file://` pages.

The dashboard normalizes common CSV header variants, explicitly coerces market cap values, and keeps all source records in its table. Valid market caps use a square-root radius scale; absent caps use one nonzero uniform radius. Every dynamically discovered sector is represented in an HTML legend.

The force simulation uses per-sector `forceX` and `forceY` targets, a center force, and `forceCollide` with the displayed radius plus padding. Bubble labels are inside the interactive group with pointer events disabled. One `selectedTicker` synchronizes table and bubble highlighting.

Tooltips are populated only for company records that have `marketCap`, `country`, and `website`. The hover and movement handlers explicitly hide and return for records missing any of these fields, so ETF hover cannot leave a previously visible company tooltip displayed.

## Validation checklist

Confirm the generated output contains:

- `index.html`
- `css/style.css`
- `js/d3.v6.min.js`
- `js/visualization.js`
- `data/stock-descriptions.csv`
- `data/indiv-stock/` with every supplied history CSV

When served through HTTP, check that chart and table start side by side, all rows have the requested four columns, legend colors match sectors, ETF bubbles display no tooltip, and selecting either a bubble or table row highlights the same ticker in both views.
