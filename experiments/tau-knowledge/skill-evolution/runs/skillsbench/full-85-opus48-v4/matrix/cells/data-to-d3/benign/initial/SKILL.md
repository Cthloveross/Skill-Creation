---
name: d3-stock-bubble-dashboard
description: >-
  Build a self-contained D3.js v6 single-page web app from a stock-descriptions
  CSV (plus per-ticker price-history CSVs) that renders a sector-clustered,
  market-cap-sized bubble chart next to a data table, with an HTML legend,
  in-bubble ticker labels, conditional tooltips (suppressed for ETFs), and
  click-to-highlight linking between the chart and the table. Use when a task
  asks to "visualize stock data with D3", produce an offline index.html with
  js/d3.v6.min.js, js/visualization.js, css/style.css and a copied data/ folder,
  and arrange a bubble chart + table side by side.
---

# D3 Stock Bubble + Table Dashboard

## What this Skill produces

An offline, self-contained web app under an output directory (default
`/root/output`) with exactly this structure:

```
output/index.html
output/js/d3.v6.min.js      # real D3 v6 library bundled locally (no CDN at runtime)
output/js/visualization.js  # all data-loading + chart + table + interaction logic
output/css/style.css        # flex side-by-side layout, tooltip, highlight classes
output/data/stock-descriptions.csv
output/data/indiv-stock/*.csv   # copied input price histories
```

It satisfies every public requirement:

1. **Bubble chart** – one bubble per stock, sized by `marketCap` through a
   `d3.scaleSqrt` (area-proportional, per the background). Entities without a
   market cap (ETFs: the lowercase tickers such as `spy`, `qqq`, `gld`, ...)
   get a **uniform default radius**.
2. **Sector clustering** – bubbles are colored by sector (ordinal color scale),
   positioned with `d3.forceX`/`d3.forceY` toward per-sector cluster centers,
   with `d3.forceCollide` to prevent overlap. An **HTML** `<div id="legend">`
   lists every sector present (ETFs that have no sector are grouped under the
   label `ETF` so they still get a swatch).
3. Cluster centers are spread across the middle of the chart and kept centered.
4. `forceCollide(radius+padding)` with a radius accessor matching the rendered
   circle radius guarantees no overlap. The simulation is **pre-ticked** so the
   layout is immediately stable for headless rendering/grading.
5. Each bubble is a `<g>` group containing a `<circle>` and a centered `<text>`
   ticker label; `text` has `pointer-events:none` and handlers are on the group
   so hover/click never hit a dead zone.
6. Hovering a bubble shows a tooltip with ticker, name, sector. The handler
   **returns early for ETFs** (no marketCap/country/website) so no tooltip is
   shown for them.
- **Table** – all stocks in a scrollable table with columns exactly
  `Ticker symbol`, `Full company name`, `Sector`, `Market cap`; the market cap
  is formatted human-readably (e.g. `1.64T`, `320B`, `-` when absent).
- **Linking** – clicking a bubble highlights its table row (and scrolls it into
  view); clicking a row highlights the matching bubble. A single `selected`
  state drives both, toggling a `selected` CSS class.

## How to run it (executor)

The end-to-end entrypoint is `scripts/build_viz.py`. It reads a small JSON
config on stdin and writes all output files, then prints a JSON report on
stdout. Run from the task container:

```bash
echo '{}' | python3 /app/environment/skills/current/scripts/build_viz.py
```

With `{}` it uses the task defaults:
`descriptions=/root/data/stock-descriptions.csv`,
`indiv_dir=/root/data/indiv-stock`, `output_dir=/root/output`.
Override any of them, e.g.:

```bash
echo '{"descriptions":"/root/data/stock-descriptions.csv",
       "indiv_dir":"/root/data/indiv-stock",
       "output_dir":"/root/output"}' \
  | python3 .../scripts/build_viz.py
```

### stdin schema
- `descriptions` (str, optional): path to the stock descriptions CSV.
- `indiv_dir` (str, optional): directory of per-ticker price-history CSVs.
- `output_dir` (str, optional): where to write the web app.
- `d3_path` (str, optional): path to an existing `d3.v6.min.js` to copy instead
  of downloading.

### stdout report (JSON)
`{"status":"ok"|"error", "output_dir":..., "files":[...], "num_rows":N,
  "columns":[...], "resolved_fields":{...}, "d3_source":"download|local|cache",
  "d3_bytes":N, "message":...}`.

### D3 bundling
The script obtains `d3.v6.min.js` in this order: (1) `d3_path` if given,
(2) an already-present `output/js/d3.v6.min.js`, (3) any copy it can find under
common container paths, (4) download from the D3 mirrors (the task environment
has `allow_internet=true`). The resulting file is validated to be a real,
non-trivial D3 build (contains the D3 version banner and is tens of KB). If none
succeeds it exits non-zero with a clear message — do **not** fabricate a stub,
because the background warns a broken/CDN D3 makes every API call fail.

## Column resolution (robust to unknown headers)
`build_viz.py` inspects the CSV header and resolves the ticker/name/sector/
marketCap columns from candidate name lists, injecting the resolved map into
`visualization.js` as `FIELD_MAP`. `visualization.js` also re-resolves at runtime
(case-insensitive) so it still works if the header differs. If a required
column cannot be resolved the report lists it as `null` under
`resolved_fields`; inspect the CSV header and extend the candidate lists in
`references/visualization.js.tmpl` and `scripts/build_viz.py` rather than
hardcoding one instance's column names.

## Validation (run after building)
`scripts/validate_output.py` reads `{"output_dir":...}` on stdin and checks:
all required files exist; `index.html` references the local d3, visualization.js
and style.css; `d3.v6.min.js` is a real library; `visualization.js` contains
`forceX`, `forceY`, `forceCollide`, `scaleSqrt`, the ETF tooltip guard and the
highlight linking; the table header has the four required column titles; and the
`data/` copy exists. It prints `{"ok":bool,"checks":[...]}`. Use it as a quick
structural gate; it does not run a browser.

```bash
echo '{"output_dir":"/root/output"}' | python3 .../scripts/validate_output.py
```

To verify runtime behavior, optionally serve the folder
(`python3 -m http.server -d /root/output`) and load it; CSVs must be loaded over
HTTP (file:// triggers CORS, per the background).

## Notes / failure handling
- The force simulation is pre-ticked (`simulation.stop()` + a tick loop) so
  bubbles have stable, non-overlapping positions without waiting for async
  cooling — important for automated DOM inspection.
- ETFs are detected by an empty/missing market cap, not by a hardcoded ticker
  list, so the logic generalizes.
- Market-cap formatting uses explicit T/B/M/K thresholds (not D3 SI `G`), per
  the financial convention in the background.
- Re-running the entrypoint regenerates all outputs idempotently.
