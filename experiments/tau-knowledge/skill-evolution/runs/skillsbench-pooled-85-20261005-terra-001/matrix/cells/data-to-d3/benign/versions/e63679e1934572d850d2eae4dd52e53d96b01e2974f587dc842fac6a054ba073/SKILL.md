---
name: d3-stock-cluster-dashboard
description: Build a self-contained D3.js v6 single-page stock dashboard from a stock-description CSV and a directory of individual stock CSV files. Use when a task requires sector-clustered, collision-free market-cap bubbles, a linked stock table, conditional tooltips, and a local copy of D3 and source data.
---

# D3 Stock Cluster Dashboard

Use `scripts/build_stock_dashboard.py` to create the requested web app. It reads the supplied data at execution time; it does not embed stock identities or market-cap values in the Skill.

## Runtime interface

The script receives one JSON object on stdin and returns one JSON object on stdout.

```json
{
  "source_data": "/root/data",
  "output_dir": "/root/output",
  "d3_source": "/optional/local/d3.v6.min.js",
  "d3_url": "https://d3js.org/d3.v6.min.js"
}
```

- `source_data` must contain `stock-descriptions.csv` and `indiv-stock/`.
- `output_dir` is created if necessary. Required app files are written below it.
- Supply `d3_source` when a local D3 v6 distribution is already available. Otherwise the script downloads the public v6 distribution from `d3_url` and stores it locally as `js/d3.v6.min.js`.
- `d3_url` is optional and defaults to the documented D3 v6 URL.

Example executor invocation:

```sh
python3 scripts/build_stock_dashboard.py <<'JSON'
{"source_data":"/root/data","output_dir":"/root/output"}
JSON
```

The successful response lists the generated paths and copied-data count. A failed prerequisite, copy operation, or D3 acquisition emits `{ "ok": false, "error": "..." }` and exits nonzero.

## Produced application behavior

The generated `index.html` loads its local D3 v6 file before `visualization.js`; `visualization.js` loads `data/stock-descriptions.csv`. It should be served from the output directory through an HTTP server because browser security normally blocks CSV fetches from `file://` pages.

The dashboard dynamically normalizes common CSV field-name variants, explicitly converts the market-cap field to a number, and keeps every CSV record in its table. It uses a square-root radius scale for valid market caps and a nonzero uniform radius for records without a market cap. Sectors are dynamically derived from the data, so the HTML legend covers every displayed category.

The visualization applies per-sector `forceX` and `forceY` targets, a centering force, and `forceCollide` whose radius accessor is exactly the circle radius plus padding. Labels are child text of the same interactive bubble group and have pointer events disabled. One `selectedTicker` state synchronizes highlight classes on table rows and bubbles. Tooltip eligibility requires market cap, country, and website, which suppresses ETF tooltips as requested.

## Validation checklist

After execution, confirm that all of these exist under `output_dir`:

- `index.html`
- `css/style.css`
- `js/d3.v6.min.js`
- `js/visualization.js`
- `data/stock-descriptions.csv`
- `data/indiv-stock/` with copied source CSVs

When served over HTTP, verify that the chart and table appear side by side, that the legend entries match the sector colors, that every table row has four requested columns, and that a selection made in either view highlights the same ticker in the other view.
