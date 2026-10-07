---
name: d3-sector-bubble-table
summary: Build a self-contained D3 v6 single-page application that displays CSV stock/company records as a sector-clustered, collision-free bubble chart linked to an accessible data table.
---

# D3 sector bubble chart and linked table

Use this Skill when the input is a company/stock-description CSV and the required deliverable is a local D3 v6 web app with a force-directed sector bubble chart, a linked table, copied source data, and no CDN dependency at runtime.

## Entry point

Run the generator with JSON on stdin:

```sh
python3 scripts/build_stock_app.py <<'JSON'
{"source_root":"/root/data","output_root":"/root/output"}
JSON
```

Input schema:

- `source_root` (string, required): directory containing `stock-descriptions.csv`; an optional `indiv-stock/` directory is copied too.
- `output_root` (string, required): directory where the web app is created.
- `d3_url` (optional string): a D3 v6 distribution URL. The default is the official `https://d3js.org/d3.v6.min.js`.

The script emits a JSON object to stdout with `ok`, `output_root`, and generated `files`. It exits nonzero with an explanatory JSON error if the source CSV is absent, the D3 download fails, or mandatory generated files cannot be validated.

## Method

1. Read the supplied CSV only at execution time. The browser code uses `d3.csv`, preserving quoted CSV fields, and normalizes common header variants for ticker, company name, sector, market cap, country, and website.
2. Copy the entire supplied source-data tree to `output_root/data`, including price-history files when available. Download D3 v6 into `output_root/js/d3.v6.min.js`, then load it before `visualization.js`.
3. Create an HTML layout with chart and table panels in one flex row. The table has the requested headers and a scrollable body region.
4. Use a square-root market-cap radius scale for valid company market caps; records without market cap receive one uniform default radius. The same `radius` value is used by rendering and `forceCollide` (with padding).
5. Build one force simulation with per-sector `forceX`/`forceY` targets, a central force, containment forces, and collision handling. Update both circle and text coordinates on every tick.
6. Assign categorical colors once and reuse the scale for all circles and every HTML legend item. Labels are centered and have `pointer-events: none`.
7. Maintain one selected ticker state. Selecting either a bubble group or its table row updates both highlight classes. Tooltips use a single non-interactive DOM node and are suppressed for incomplete ETF-style records.

## Validation and use

After generation, verify that `index.html`, `js/d3.v6.min.js`, `js/visualization.js`, `css/style.css`, and `data/stock-descriptions.csv` exist and that the D3 file is nonempty. The generator performs these checks itself.

Serve `output_root` with a local HTTP server before opening `index.html`, because browsers usually block `fetch`/`d3.csv` requests from a `file://` page. For example, from the output directory use an available static HTTP server and browse to its `index.html`. Confirm that the page shows one bubble per CSV record, all sector legend labels, the four requested table columns, market-cap placeholders for missing values, and bidirectional selection highlighting.

If source headers use an unsupported naming convention, update the `FIELD_ALIASES` map in the generated `js/visualization.js`; do not fabricate company data or infer market caps from price histories.
