---
name: stock-sector-force-bubbles
summary: Build an offline-served D3 v6 stock dashboard with a sector-clustered bubble chart and linked table.
description: Use when a task requires a local D3 v6 single-page visualization of a stock-description CSV, including market-cap-sized sector bubbles, an HTML legend, ETF tooltip suppression, readable financial values, copied input data, and bidirectional table/chart selection.
---

# Stock sector force-bubble dashboard

Run `scripts/build_stock_bubbles.py` with one JSON object on stdin. It creates these files below `output_dir`:

- `index.html`
- `css/style.css`
- `js/d3.v6.min.js`
- `js/visualization.js`
- `data/`, recursively copied from `source_dir`

## Input schema

```json
{
  "source_dir": "/root/data",
  "output_dir": "/root/output",
  "d3_url": "https://d3js.org/d3.v6.min.js"
}
```

`source_dir` must contain `stock-descriptions.csv`. `d3_url` is optional. The builder uses Python standard-library modules only, writes one JSON result to stdout, and exits nonzero after reporting `{ "ok": false, "error": "..." }` if a prerequisite, copy, download, or validation step fails.

Example:

```bash
python3 scripts/build_stock_bubbles.py <<'JSON'
{"source_dir":"/root/data","output_dir":"/root/output"}
JSON
```

Serve the resulting output directory over local HTTP when viewing it. The browser application intentionally reads the copied CSV through D3, which is not reliably permitted from `file://` URLs.

## Generated application behavior

The generated page loads its local D3 v6 asset before visualization logic and parses the copied CSV with explicit market-cap conversion. It recognizes common header variants for ticker, company name, sector, market cap, country, and website. Missing market cap is represented as `null`, gets one uniform ETF radius, displays as an em dash in the table, and directly suppresses its tooltip. Records also require country and website before their tooltip is shown.

Bubble radius uses `d3.scaleSqrt`; sector centers drive both `forceX` and `forceY`; `forceCenter` keeps the layout centered; and collision uses the same stored radius used for rendered circles. Labels move with their parent node and have pointer events disabled. The HTML legend includes all sectors in the CSV. One selected ticker applies the selected class to both the bubble group and matching table row.

## Validation

The builder verifies the source CSV, recursively copies supplied data, validates a nonempty local D3 distribution, and confirms every declared output file exists and is nonempty. Once served, verify that the status reports the loaded row count, every sector appears in the legend, missing market caps are not rendered as `NaN` or `undefined`, ETF bubbles show no tooltip, and clicks in either view select the matching item in both views.
