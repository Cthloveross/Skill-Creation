#!/usr/bin/env python3
"""Generate a local D3 v6 stock-cluster dashboard.

Input JSON schema:
{
  "source_data": "/path/containing/stock-descriptions.csv",
  "output_dir": "/path/to/create",
  "d3_source": "/optional/local/d3.v6.min.js",
  "d3_url": "optional URL used if d3_source is absent"
}

Output JSON schema:
{"ok": true, "output_dir": "...", "files": ["..."], "copied_history_files": 50}
or, on failure, {"ok": false, "error": "..."}.
"""

import json
import shutil
import sys
import urllib.request
from pathlib import Path

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Sector Explorer</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body>
  <main>
    <header class="page-header">
      <div><p class="eyebrow">MARKET OVERVIEW</p><h1>Stock Sector Explorer</h1></div>
      <p class="subtitle">Bubble area represents market capitalization. Select a bubble or table row to link the views.</p>
    </header>
    <p id="load-error" class="load-error" role="alert" hidden></p>
    <section id="dashboard" aria-label="Linked stock visualizations">
      <section class="panel chart-panel" aria-labelledby="chart-title">
        <div class="panel-heading"><div><h2 id="chart-title">Companies by sector</h2><p>Color identifies sector; bubbles are clustered with a force simulation.</p></div></div>
        <svg id="bubble-chart" viewBox="0 0 760 620" role="img" aria-label="Force-directed bubbles for stocks grouped by sector"></svg>
        <div class="legend-wrap"><h3>Sector legend</h3><div id="legend" class="legend" aria-label="Sector color legend"></div></div>
      </section>
      <section class="panel table-panel" aria-labelledby="table-title">
        <div class="panel-heading"><div><h2 id="table-title">All stocks</h2><p>Click a row to select its corresponding bubble.</p></div><span id="stock-count" class="count"></span></div>
        <div class="table-scroll"><table id="stock-table"><thead><tr><th scope="col">Ticker symbol</th><th scope="col">Full company name</th><th scope="col">Sector</th><th scope="col">Market cap</th></tr></thead><tbody></tbody></table></div>
      </section>
    </section>
  </main>
  <div id="tooltip" class="tooltip" role="tooltip" aria-hidden="true"></div>
  <script src="js/d3.v6.min.js"></script>
  <script src="js/visualization.js"></script>
</body>
</html>
"""

STYLE_CSS = """:root { color-scheme: light; --ink:#17233a; --muted:#61708a; --line:#dce3ed; --surface:#fff; --page:#f4f7fb; --accent:#1f5fbf; }
* { box-sizing:border-box; }
body { margin:0; background:var(--page); color:var(--ink); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
main { max-width:1600px; margin:0 auto; padding:28px; }
.page-header { display:flex; justify-content:space-between; gap:28px; align-items:end; margin-bottom:22px; }
h1,h2,h3,p { margin:0; } h1 { font-size:clamp(1.65rem,3vw,2.4rem); letter-spacing:-.035em; } h2 { font-size:1.12rem; } h3 { font-size:.86rem; margin-bottom:8px; }
.eyebrow { color:var(--accent); font-size:.72rem; font-weight:800; letter-spacing:.12em; margin-bottom:5px; }.subtitle,.panel-heading p { color:var(--muted); font-size:.87rem; line-height:1.45; }.subtitle { max-width:440px; text-align:right; }
#dashboard { display:grid; grid-template-columns:minmax(560px,1.25fr) minmax(460px,1fr); gap:22px; align-items:start; }.panel { min-width:0; background:var(--surface); border:1px solid var(--line); border-radius:14px; box-shadow:0 4px 18px rgba(22,43,77,.06); overflow:hidden; }.panel-heading { display:flex; justify-content:space-between; gap:12px; padding:18px 20px 10px; }.panel-heading p { margin-top:4px; }.count { align-self:start; white-space:nowrap; border-radius:99px; padding:4px 9px; background:#eaf1fc; color:#285ca5; font-size:.76rem; font-weight:700; }
#bubble-chart { display:block; width:100%; height:auto; min-height:440px; }.bubble { cursor:pointer; outline:none; }.bubble circle { stroke:rgba(20,36,63,.28); stroke-width:1.4px; transition:stroke-width .14s,stroke .14s,filter .14s; }.bubble text { fill:#fff; font-size:10px; font-weight:800; text-anchor:middle; dominant-baseline:central; pointer-events:none; paint-order:stroke; stroke:rgba(16,29,50,.28); stroke-width:2px; stroke-linejoin:round; }.bubble:hover circle,.bubble:focus circle,.bubble.selected circle { stroke:#12254a; stroke-width:3.2px; filter:drop-shadow(0 2px 3px rgba(12,27,52,.25)); }.bubble.selected circle { stroke:#ffb000; }
.legend-wrap { border-top:1px solid var(--line); padding:13px 20px 18px; }.legend { display:flex; flex-wrap:wrap; gap:7px 14px; }.legend-entry { display:inline-flex; align-items:center; gap:6px; font-size:.77rem; color:#394861; }.swatch { width:11px; height:11px; flex:0 0 11px; border-radius:50%; border:1px solid rgba(0,0,0,.15); }
.table-scroll { max-height:620px; overflow:auto; border-top:1px solid var(--line); } table { width:100%; border-collapse:collapse; font-size:.82rem; } th { position:sticky; top:0; z-index:1; background:#f7f9fc; color:#44526a; text-align:left; font-size:.7rem; letter-spacing:.035em; text-transform:uppercase; } th,td { padding:11px 12px; border-bottom:1px solid #e8edf4; vertical-align:top; } td:first-child { font-weight:800; color:#244d88; } td:nth-child(2) { max-width:230px; } td:last-child { white-space:nowrap; text-align:right; font-variant-numeric:tabular-nums; } tbody tr { cursor:pointer; outline:none; transition:background .12s; } tbody tr:hover,tbody tr:focus { background:#edf4ff; } tbody tr.selected { background:#fff1c9; box-shadow:inset 4px 0 #e4a400; }.tooltip { position:fixed; z-index:10; max-width:260px; padding:10px 12px; border-radius:8px; color:#f8fbff; background:#13233d; box-shadow:0 8px 22px rgba(8,18,36,.24); font-size:.8rem; line-height:1.45; opacity:0; pointer-events:none; transform:translateY(5px); transition:opacity .14s,transform .14s; }.tooltip.visible { opacity:1; transform:translateY(0); }.tooltip strong { display:block; font-size:.9rem; }.tooltip span { color:#d4dfef; }.load-error { margin:0 0 15px; padding:12px; border:1px solid #e9a4a4; background:#fff1f1; color:#8d2020; border-radius:8px; }
@media (max-width:1080px) { #dashboard { grid-template-columns:1fr; }.subtitle { text-align:left; }.page-header { align-items:start; flex-direction:column; } .table-scroll { max-height:480px; } }
"""

VISUALIZATION_JS = r"""(() => {
  'use strict';
  const WIDTH = 760, HEIGHT = 620, PADDING = 2;
  let selectedTicker = null;
  const tooltip = d3.select('#tooltip');

  // CSV schemas vary, so resolve field names case-insensitively at runtime.
  function field(row, candidates) {
    const keys = Object.keys(row);
    for (const candidate of candidates) {
      const exact = keys.find(key => key.toLowerCase() === candidate.toLowerCase());
      if (exact && String(row[exact]).trim() !== '') return String(row[exact]).trim();
    }
    return '';
  }
  function parseNumber(value) {
    if (value === null || value === undefined || String(value).trim() === '') return null;
    const raw = String(value).trim().replace(/[$,\s]/g, '');
    const suffix = raw.slice(-1).toUpperCase();
    const multiplier = ({K:1e3, M:1e6, B:1e9, T:1e12})[suffix] || 1;
    const numeric = Number(suffix in {K:1,M:1,B:1,T:1} ? raw.slice(0, -1) : raw);
    return Number.isFinite(numeric) && numeric >= 0 ? numeric * multiplier : null;
  }
  function formatMarketCap(value) {
    if (!Number.isFinite(value)) return '—';
    const units = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']];
    for (const [threshold, suffix] of units) {
      if (value >= threshold) {
        const scaled = value / threshold;
        const digits = scaled >= 100 ? 0 : (scaled >= 10 ? 1 : 2);
        return `${scaled.toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1')}${suffix}`;
      }
    }
    return value.toLocaleString(undefined, {maximumFractionDigits: 0});
  }
  function normalize(row, index) {
    const marketCap = parseNumber(field(row, ['marketCap', 'market cap', 'market_cap', 'marketcapitalization']));
    const ticker = field(row, ['symbol', 'ticker', 'ticker symbol']) || `Record ${index + 1}`;
    const sectorValue = field(row, ['sector', 'sector name']);
    return {
      ticker, name: field(row, ['longName', 'long name', 'name', 'full company name', 'company']),
      sector: sectorValue || (marketCap === null ? 'ETF / Unclassified' : 'Unclassified'),
      marketCap, country: field(row, ['country']), website: field(row, ['website', 'web site']), raw: row
    };
  }
  function positionTooltip(event) {
    const margin = 14;
    const node = tooltip.node();
    const left = Math.min(window.innerWidth - node.offsetWidth - margin, event.clientX + margin);
    const top = Math.min(window.innerHeight - node.offsetHeight - margin, event.clientY + margin);
    tooltip.style('left', `${Math.max(margin, left)}px`).style('top', `${Math.max(margin, top)}px`);
  }
  function showTooltip(event, d) {
    // ETFs and other entries lacking the requested company-detail fields intentionally have no tooltip.
    if (!d.hasTooltip) return;
    const node = tooltip.node(); node.replaceChildren();
    const title = document.createElement('strong'); title.textContent = d.ticker;
    const name = document.createElement('span'); name.textContent = d.name || 'Company name unavailable';
    const sector = document.createElement('span'); sector.textContent = `Sector: ${d.sector}`;
    node.append(title, name, document.createElement('br'), sector);
    tooltip.classed('visible', true).attr('aria-hidden', 'false'); positionTooltip(event);
  }
  function hideTooltip() { tooltip.classed('visible', false).attr('aria-hidden', 'true'); }

  function displayError(message) {
    d3.select('#load-error').text(message).attr('hidden', null);
  }

  d3.csv('data/stock-descriptions.csv').then(rows => {
    if (!rows.length) throw new Error('The stock-description CSV contains no records.');
    const data = rows.map(normalize);
    const capValues = data.map(d => d.marketCap).filter(Number.isFinite);
    const fallbackRadius = 16;
    const radiusScale = capValues.length
      ? d3.scaleSqrt().domain(d3.extent(capValues)).range([11, 34]).clamp(true)
      : () => fallbackRadius;
    data.forEach(d => {
      d.r = Number.isFinite(d.marketCap) ? radiusScale(d.marketCap) : fallbackRadius;
      d.hasTooltip = Number.isFinite(d.marketCap) && Boolean(d.country) && Boolean(d.website);
    });

    const sectors = Array.from(new Set(data.map(d => d.sector))).sort(d3.ascending);
    const palette = (d3.schemeTableau10 || []).concat(d3.schemeSet3 || [], d3.schemePaired || []);
    const color = d3.scaleOrdinal(sectors, palette);
    const cols = Math.max(1, Math.ceil(Math.sqrt(sectors.length * 1.45)));
    const rowsNeeded = Math.ceil(sectors.length / cols);
    const centers = new Map(sectors.map((sector, i) => [sector, {
      x: 110 + (i % cols) * ((WIDTH - 220) / Math.max(1, cols - 1)),
      y: 115 + Math.floor(i / cols) * ((HEIGHT - 230) / Math.max(1, rowsNeeded - 1))
    }]));

    d3.select('#stock-count').text(`${data.length} records`);
    const legend = d3.select('#legend').selectAll('.legend-entry').data(sectors).join('div').attr('class', 'legend-entry');
    legend.append('span').attr('class', 'swatch').style('background-color', color);
    legend.append('span').text(d => d);

    const tbody = d3.select('#stock-table tbody');
    const tableRows = tbody.selectAll('tr').data(data, d => d.ticker).join('tr')
      .attr('data-ticker', d => d.ticker).attr('tabindex', 0).attr('role', 'button')
      .attr('aria-label', d => `Select ${d.ticker}`)
      .on('click', (event, d) => selectTicker(d.ticker, true))
      .on('keydown', (event, d) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectTicker(d.ticker, true); } });
    tableRows.append('td').text(d => d.ticker);
    tableRows.append('td').text(d => d.name || '—');
    tableRows.append('td').text(d => d.sector);
    tableRows.append('td').text(d => formatMarketCap(d.marketCap));

    const svg = d3.select('#bubble-chart');
    const bubbleGroups = svg.selectAll('g.bubble').data(data, d => d.ticker).join('g')
      .attr('class', 'bubble').attr('data-ticker', d => d.ticker).attr('tabindex', 0).attr('role', 'button')
      .attr('aria-label', d => `${d.ticker}, ${d.sector}`)
      .on('click', (event, d) => selectTicker(d.ticker, true))
      .on('keydown', (event, d) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectTicker(d.ticker, true); } })
      .on('mouseenter', showTooltip).on('mousemove', (event, d) => { if (d.hasTooltip) positionTooltip(event); }).on('mouseleave', hideTooltip);
    bubbleGroups.append('circle').attr('r', d => d.r).attr('fill', d => color(d.sector));
    bubbleGroups.append('text').text(d => d.ticker).style('font-size', d => `${Math.max(7, Math.min(11, d.r * .43))}px`);

    function selectTicker(ticker, scrollRow) {
      selectedTicker = ticker;
      bubbleGroups.classed('selected', d => d.ticker === selectedTicker).attr('aria-pressed', d => d.ticker === selectedTicker ? 'true' : 'false');
      tableRows.classed('selected', d => d.ticker === selectedTicker).attr('aria-pressed', d => d.ticker === selectedTicker ? 'true' : 'false');
      if (scrollRow) {
        const row = tableRows.filter(d => d.ticker === selectedTicker).node();
        if (row) row.scrollIntoView({block: 'nearest', behavior: 'smooth'});
      }
    }

    // The circle r and this collision-radius accessor deliberately share d.r.
    const simulation = d3.forceSimulation(data)
      .force('x', d3.forceX(d => centers.get(d.sector).x).strength(.15))
      .force('y', d3.forceY(d => centers.get(d.sector).y).strength(.15))
      .force('collide', d3.forceCollide(d => d.r + PADDING).iterations(3))
      .force('center', d3.forceCenter(WIDTH / 2, HEIGHT / 2).strength(.08))
      .alpha(1).alphaDecay(.035)
      .on('tick', () => {
        data.forEach(d => { d.x = Math.max(d.r, Math.min(WIDTH - d.r, d.x)); d.y = Math.max(d.r, Math.min(HEIGHT - d.r, d.y)); });
        bubbleGroups.attr('transform', d => `translate(${d.x},${d.y})`);
      });
    // Retain the simulation reference for browser debugging while it cools.
    window.stockBubbleSimulation = simulation;
  }).catch(error => {
    console.error(error);
    displayError(`Could not load stock data: ${error.message}. Serve this folder through a local HTTP server and confirm data/stock-descriptions.csv is present.`);
  });
})();
"""


def acquire_d3(destination: Path, supplied_source: str | None, url: str) -> None:
    if supplied_source:
        source = Path(supplied_source)
        if not source.is_file():
            raise FileNotFoundError(f"d3_source does not exist or is not a file: {source}")
        shutil.copy2(source, destination)
    else:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "stock-dashboard-builder/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
        except Exception as exc:
            raise RuntimeError(f"Unable to download local D3 v6 from {url}: {exc}. Supply d3_source to use a local copy.") from exc
        if len(payload) < 10000 or b"d3" not in payload.lower():
            raise RuntimeError("Downloaded D3 payload is unexpectedly small or invalid.")
        destination.write_bytes(payload)
    if destination.stat().st_size < 10000:
        raise RuntimeError("Local d3.v6.min.js is unexpectedly small; refusing to generate a broken app.")


def build(config: dict) -> dict:
    source_data = Path(config.get("source_data", "/root/data")).expanduser().resolve()
    output_dir = Path(config.get("output_dir", "/root/output")).expanduser().resolve()
    descriptions = source_data / "stock-descriptions.csv"
    history_dir = source_data / "indiv-stock"
    if not descriptions.is_file():
        raise FileNotFoundError(f"Missing required CSV: {descriptions}")
    if not history_dir.is_dir():
        raise FileNotFoundError(f"Missing required individual-stock directory: {history_dir}")

    (output_dir / "js").mkdir(parents=True, exist_ok=True)
    (output_dir / "css").mkdir(parents=True, exist_ok=True)
    data_out = output_dir / "data"
    data_out.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (output_dir / "css" / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (output_dir / "js" / "visualization.js").write_text(VISUALIZATION_JS, encoding="utf-8")
    shutil.copy2(descriptions, data_out / "stock-descriptions.csv")
    shutil.copytree(history_dir, data_out / "indiv-stock", dirs_exist_ok=True)
    acquire_d3(output_dir / "js" / "d3.v6.min.js", config.get("d3_source"), config.get("d3_url", "https://d3js.org/d3.v6.min.js"))

    expected = [
        output_dir / "index.html", output_dir / "css" / "style.css", output_dir / "js" / "visualization.js",
        output_dir / "js" / "d3.v6.min.js", data_out / "stock-descriptions.csv", data_out / "indiv-stock"
    ]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise RuntimeError("Generation validation failed; missing: " + ", ".join(missing))
    history_count = sum(1 for path in (data_out / "indiv-stock").rglob("*") if path.is_file())
    return {"ok": True, "output_dir": str(output_dir), "files": [str(path) for path in expected], "copied_history_files": history_count}


def main() -> None:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(build(config)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
