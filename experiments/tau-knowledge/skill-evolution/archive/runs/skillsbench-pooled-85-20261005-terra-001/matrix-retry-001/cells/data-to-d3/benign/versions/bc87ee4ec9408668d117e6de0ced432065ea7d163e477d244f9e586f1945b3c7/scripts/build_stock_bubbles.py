#!/usr/bin/env python3
"""Create a local D3 v6 stock-sector force-bubble web app.

Reads one JSON object from stdin and writes one JSON result object to stdout.
"""
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

DEFAULT_D3_URL = "https://d3js.org/d3.v6.min.js"

INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock market capitalization by sector</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body>
  <main class="page-shell">
    <header class="page-header">
      <h1>Stock market capitalization by sector</h1>
      <p>Bubble area encodes market capitalization. Select a bubble or table row to link the two views.</p>
    </header>
    <div id="load-status" class="load-status" role="status" aria-live="polite">Loading stock descriptions…</div>
    <section class="dashboard" aria-label="Linked stock chart and table">
      <section class="chart-panel" aria-labelledby="bubble-heading">
        <div class="panel-heading">
          <h2 id="bubble-heading">Sector-clustered bubbles</h2>
          <span class="hint">Hover a company bubble for details</span>
        </div>
        <svg id="bubble-chart" viewBox="0 0 760 590" role="img" aria-label="Bubbles clustered by stock sector"></svg>
        <div id="legend" class="legend" aria-label="Sector color legend"></div>
      </section>
      <section class="table-panel" aria-labelledby="table-heading">
        <div class="panel-heading"><h2 id="table-heading">All stocks</h2></div>
        <div class="table-scroll">
          <table id="stock-table">
            <thead><tr><th scope="col">Ticker symbol</th><th scope="col">Full company name</th><th scope="col">Sector</th><th scope="col">Market cap</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </section>
    </section>
  </main>
  <div id="tooltip" class="tooltip" role="tooltip" aria-hidden="true"></div>
  <script src="js/d3.v6.min.js"></script>
  <script src="js/visualization.js"></script>
</body>
</html>
'''

STYLE_CSS = r'''* { box-sizing: border-box; }
:root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; color: #172033; background: #f5f7fb; }
body { margin: 0; }
.page-shell { max-width: 1500px; margin: 0 auto; padding: 24px; }
.page-header { margin-bottom: 14px; }
h1 { margin: 0 0 6px; color: #12213a; font-size: clamp(1.45rem, 2.6vw, 2.1rem); }
h2 { margin: 0; color: #182743; font-size: 1.05rem; }
.page-header p, .hint { color: #5d6a7e; margin: 0; font-size: .92rem; }
.load-status { min-height: 1.35rem; margin: 0 0 12px; color: #43526c; font-size: .9rem; }
.load-status.error { color: #a51627; font-weight: 600; }
.dashboard { display: flex; align-items: flex-start; gap: 20px; }
.chart-panel, .table-panel { background: #fff; border: 1px solid #dce3ef; border-radius: 10px; box-shadow: 0 2px 7px rgba(26, 47, 82, .06); }
.chart-panel { flex: 1.15 1 680px; min-width: 0; padding: 14px; }
.table-panel { flex: .85 1 500px; min-width: 0; padding: 14px; }
.panel-heading { min-height: 30px; display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
#bubble-chart { display: block; width: 100%; height: auto; min-height: 405px; overflow: visible; }
.cluster-label { fill: #6f7e95; font-size: 11px; font-weight: 650; text-anchor: middle; pointer-events: none; }
.bubble-node { cursor: pointer; outline: none; }
.bubble { stroke: #fff; stroke-width: 1.7px; transition: stroke-width .15s, stroke .15s, opacity .15s; }
.bubble-node:hover .bubble, .bubble-node:focus .bubble { stroke: #172033; stroke-width: 3px; }
.bubble-node.is-selected .bubble { stroke: #111827; stroke-width: 4px; }
.bubble-label { fill: #fff; font-size: 11px; font-weight: 750; text-anchor: middle; dominant-baseline: central; pointer-events: none; user-select: none; paint-order: stroke; stroke: rgba(20, 31, 47, .42); stroke-width: 2px; stroke-linejoin: round; }
.legend { display: flex; flex-wrap: wrap; gap: 7px 14px; padding: 3px 2px 0; }
.legend-entry { display: inline-flex; align-items: center; gap: 6px; color: #3e4d65; font-size: .82rem; }
.legend-swatch { width: 12px; height: 12px; display: inline-block; border-radius: 3px; border: 1px solid rgba(0,0,0,.16); }
.table-scroll { max-height: 570px; overflow: auto; border: 1px solid #e4e9f1; border-radius: 6px; }
table { width: 100%; border-collapse: collapse; font-size: .84rem; }
thead { position: sticky; top: 0; z-index: 1; background: #edf2f8; }
th { text-align: left; color: #34435b; font-size: .76rem; letter-spacing: .01em; white-space: nowrap; }
th, td { padding: 9px 10px; border-bottom: 1px solid #e8edf4; vertical-align: top; }
td:nth-child(1), td:nth-child(3), td:nth-child(4) { white-space: nowrap; }
td:nth-child(2) { min-width: 160px; }
tbody tr { cursor: pointer; transition: background-color .14s; }
tbody tr:hover, tbody tr:focus { background: #eff6ff; outline: none; }
tbody tr.is-selected { background: #fef3c7; box-shadow: inset 4px 0 #d97706; font-weight: 600; }
.tooltip { position: fixed; z-index: 10; max-width: 250px; padding: 9px 11px; border-radius: 6px; color: white; background: rgba(19, 31, 50, .94); font-size: .84rem; line-height: 1.4; box-shadow: 0 3px 14px rgba(0,0,0,.22); opacity: 0; pointer-events: none; transform: translate(12px, 12px); transition: opacity .15s ease; }
.tooltip.is-visible { opacity: 1; }
.tooltip strong { display: block; font-size: .94rem; }
@media (max-width: 980px) { .dashboard { flex-direction: column; } .chart-panel, .table-panel { width: 100%; flex-basis: auto; } .table-scroll { max-height: 420px; } }
@media (max-width: 560px) { .page-shell { padding: 14px; } .panel-heading { align-items: flex-start; flex-direction: column; gap: 3px; } th, td { padding: 8px 7px; } }
'''

VISUALIZATION_JS = r'''(() => {
  "use strict";
  const W = 760, H = 590, PADDING = 20, ETF_RADIUS = 18;
  const status = d3.select("#load-status");
  const tooltip = d3.select("#tooltip");
  const svg = d3.select("#bubble-chart");
  let selectedTicker = null;

  function text(value) { return value == null ? "" : String(value).trim(); }
  function keyOf(value) { return text(value).toLowerCase().replace(/[^a-z0-9]/g, ""); }
  function valueFrom(row, aliases) {
    const wanted = new Set(aliases.map(keyOf));
    for (const [name, value] of Object.entries(row)) if (wanted.has(keyOf(name)) && text(value)) return text(value);
    return "";
  }
  function parseNumber(value) {
    const input = text(value).replace(/[$,\s]/g, "");
    if (!input || /^(n\/?a|null|undefined|-)$/i.test(input)) return null;
    const match = input.match(/^(-?[\d.]+)([kmbt])?$/i);
    if (!match) return null;
    const amount = Number(match[1]);
    const multipliers = { k: 1e3, m: 1e6, b: 1e9, t: 1e12 };
    const result = amount * (multipliers[(match[2] || "").toLowerCase()] || 1);
    return Number.isFinite(result) ? result : null;
  }
  function normalize(row, index) {
    const ticker = valueFrom(row, ["symbol", "ticker", "ticker symbol", "tickersymbol"]) || `Record ${index + 1}`;
    const name = valueFrom(row, ["longName", "long name", "company name", "full company name", "name", "shortName", "short name"]) || ticker;
    const sector = valueFrom(row, ["sector", "industry sector"]) || "Unclassified";
    const marketCap = parseNumber(valueFrom(row, ["marketCap", "market cap", "market capitalization", "marketcapitalization"]));
    const country = valueFrom(row, ["country"]);
    const website = valueFrom(row, ["website", "web site", "url"]);
    return { ticker, name, sector, marketCap, country, website, hasDetails: marketCap !== null && !!country && !!website };
  }
  function formatFinancial(value) {
    if (!Number.isFinite(value)) return "—";
    const magnitude = Math.abs(value);
    const suffixes = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
    for (const [threshold, suffix] of suffixes) {
      if (magnitude >= threshold) {
        const scaled = value / threshold;
        return `${scaled.toFixed(scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2).replace(/\.0+$|(?<=\.[0-9])0$/, "")}${suffix}`;
      }
    }
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  function safeId(value) { return String(value).replace(/[^a-zA-Z0-9_-]/g, "_"); }
  function positionTooltip(event) { tooltip.style("left", `${event.clientX}px`).style("top", `${event.clientY}px`); }
  function hideTooltip() { tooltip.classed("is-visible", false).attr("aria-hidden", "true"); }

  d3.csv("data/stock-descriptions.csv", normalize).then(records => {
    const data = records.filter(d => d.ticker);
    if (!data.length) throw new Error("The CSV did not contain any readable stock records.");
    const sectors = Array.from(new Set(data.map(d => d.sector))).sort(d3.ascending);
    const colors = d3.scaleOrdinal().domain(sectors).range(d3.schemeTableau10.concat(d3.schemeSet3));
    const caps = data.map(d => d.marketCap).filter(Number.isFinite);
    const extent = d3.extent(caps);
    const radiusScale = d3.scaleSqrt().domain(extent[0] === extent[1] ? [0, extent[1] || 1] : extent).range([13, 47]);
    data.forEach(d => { d.radius = Number.isFinite(d.marketCap) ? radiusScale(d.marketCap) : ETF_RADIUS; });

    const columns = Math.max(1, Math.ceil(Math.sqrt(sectors.length)));
    const rows = Math.ceil(sectors.length / columns);
    const centers = new Map(sectors.map((sector, i) => [sector, {
      x: PADDING + (i % columns + .5) * ((W - 2 * PADDING) / columns),
      y: 55 + (Math.floor(i / columns) + .5) * ((H - 105) / rows)
    }]));
    data.forEach((d, i) => {
      const c = centers.get(d.sector);
      d.x = c.x + ((i % 5) - 2) * 4;
      d.y = c.y + (Math.floor(i / 5) % 3 - 1) * 4;
    });

    svg.append("g").attr("class", "cluster-labels").selectAll("text")
      .data(sectors).join("text").attr("class", "cluster-label")
      .attr("x", d => centers.get(d).x).attr("y", d => centers.get(d).y - 52).text(d => d);

    const nodes = svg.append("g").attr("class", "nodes").selectAll("g")
      .data(data, d => d.ticker).join("g").attr("class", "bubble-node")
      .attr("data-ticker", d => safeId(d.ticker)).attr("role", "button").attr("tabindex", 0)
      .attr("aria-label", d => `${d.ticker}, ${d.name}. Select to highlight its table row.`);
    nodes.append("circle").attr("class", "bubble").attr("r", d => d.radius).attr("fill", d => colors(d.sector));
    nodes.append("text").attr("class", "bubble-label").style("font-size", d => `${Math.max(8, Math.min(11, d.radius / (d.ticker.length > 4 ? 1.15 : .9)))}px`).text(d => d.ticker);

    const rowsSelection = d3.select("#stock-table tbody").selectAll("tr").data(data, d => d.ticker).join("tr")
      .attr("data-ticker", d => safeId(d.ticker)).attr("tabindex", 0).attr("role", "button")
      .attr("aria-label", d => `Select ${d.ticker}`);
    rowsSelection.selectAll("td").data(d => [d.ticker, d.name, d.sector, formatFinancial(d.marketCap)]).join("td").text(d => d);

    d3.select("#legend").selectAll("div").data(sectors).join("div").attr("class", "legend-entry")
      .each(function(sector) { const item = d3.select(this); item.selectAll("span").data([sector]).join("span").attr("class", "legend-swatch").style("background-color", colors); item.selectAll("label").data([sector]).join("label").text(d => d); });

    function selectTicker(ticker) {
      selectedTicker = ticker;
      nodes.classed("is-selected", d => d.ticker === selectedTicker).attr("aria-pressed", d => String(d.ticker === selectedTicker));
      rowsSelection.classed("is-selected", d => d.ticker === selectedTicker).attr("aria-selected", d => String(d.ticker === selectedTicker));
      const row = rowsSelection.filter(d => d.ticker === selectedTicker).node();
      if (row) row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    function showTooltip(event, d) {
      if (!d.hasDetails) { hideTooltip(); return; }
      tooltip.html(`<strong>${escapeHTML(d.ticker)} — ${escapeHTML(d.name)}</strong><span>${escapeHTML(d.sector)}</span>`)
        .classed("is-visible", true).attr("aria-hidden", "false");
      positionTooltip(event);
    }
    function escapeHTML(value) { const el = document.createElement("div"); el.textContent = value; return el.innerHTML; }
    nodes.on("mouseenter", showTooltip).on("mousemove", (event, d) => { if (d.hasDetails) positionTooltip(event); })
      .on("mouseleave", hideTooltip).on("click", (event, d) => selectTicker(d.ticker))
      .on("keydown", (event, d) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectTicker(d.ticker); } });
    rowsSelection.on("click", (event, d) => selectTicker(d.ticker))
      .on("keydown", (event, d) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectTicker(d.ticker); } });

    function ticked() { nodes.attr("transform", d => `translate(${d.x},${d.y})`); }
    const simulation = d3.forceSimulation(data)
      .force("x", d3.forceX(d => centers.get(d.sector).x).strength(.13))
      .force("y", d3.forceY(d => centers.get(d.sector).y).strength(.13))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force("collide", d3.forceCollide().radius(d => d.radius + 2).strength(1).iterations(3))
      .on("tick", ticked);
    for (let i = 0; i < 220; i += 1) simulation.tick();
    ticked();
    simulation.alpha(.22).restart();
    status.text(`Loaded ${data.length} stocks across ${sectors.length} sector${sectors.length === 1 ? "" : "s"}.`);
  }).catch(error => {
    console.error(error);
    status.classed("error", true).text(`Unable to load stock data: ${error.message}`);
  });
})();
'''

def download_d3(destination: Path, url: str) -> None:
    if destination.exists() and destination.stat().st_size > 100000:
        return
    request = urllib.request.Request(url, headers={"User-Agent": "stock-d3-builder/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    if len(payload) < 100000 or b"d3" not in payload.lower():
        raise RuntimeError("Downloaded D3 asset is unexpectedly small or is not a D3 distribution.")
    destination.write_bytes(payload)

def build(config: dict) -> dict:
    source = Path(config.get("source_dir", "/root/data")).resolve()
    output = Path(config.get("output_dir", "/root/output")).resolve()
    descriptions = source / "stock-descriptions.csv"
    if not source.is_dir():
        raise FileNotFoundError(f"Source data directory does not exist: {source}")
    if not descriptions.is_file():
        raise FileNotFoundError(f"Required CSV not found: {descriptions}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "js").mkdir(exist_ok=True)
    (output / "css").mkdir(exist_ok=True)
    shutil.copytree(source, output / "data", dirs_exist_ok=True)
    (output / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (output / "css" / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (output / "js" / "visualization.js").write_text(VISUALIZATION_JS, encoding="utf-8")
    download_d3(output / "js" / "d3.v6.min.js", config.get("d3_url", DEFAULT_D3_URL))
    required = [output / "index.html", output / "css" / "style.css", output / "js" / "visualization.js", output / "js" / "d3.v6.min.js", output / "data" / "stock-descriptions.csv"]
    missing = [str(item) for item in required if not item.is_file() or item.stat().st_size == 0]
    if missing:
        raise RuntimeError("Build validation failed; missing or empty: " + ", ".join(missing))
    return {"ok": True, "output_dir": str(output), "files_validated": [str(x.relative_to(output)) for x in required]}

def main() -> None:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(build(config)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
