#!/usr/bin/env python3
"""Generate a local D3 v6 stock bubble/table application.
Reads one JSON request from stdin and writes one JSON result to stdout.
"""
import json
import shutil
import sys
import urllib.request
from pathlib import Path

DEFAULT_D3_URL = "https://d3js.org/d3.v6.min.js"
# Equivalent official v6 distribution mirrors.  A browser never needs network access:
# this is used only once by the generator to write the local artifact.
D3_FALLBACK_URLS = (
    "https://cdn.jsdelivr.net/npm/d3@6/dist/d3.min.js",
    "https://unpkg.com/d3@6/dist/d3.min.js",
)

HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Stock sectors: market-cap bubbles</title>
  <link rel=\"stylesheet\" href=\"css/style.css\">
</head>
<body>
  <main class=\"page\">
    <header><h1>Stock market capitalization by sector</h1><p>Bubble area represents market capitalization. Select a bubble or a table row to link the two views.</p></header>
    <section id=\"dashboard\" aria-label=\"Linked bubble chart and stock table\">
      <section class=\"panel chart-panel\" aria-labelledby=\"chart-heading\">
        <h2 id=\"chart-heading\">Sector clusters</h2>
        <div id=\"chart\" aria-label=\"Force-directed stock bubbles\"></div>
        <div id=\"legend\" class=\"legend\" aria-label=\"Sector color legend\"></div>
      </section>
      <section class=\"panel table-panel\" aria-labelledby=\"table-heading\">
        <h2 id=\"table-heading\">All stocks</h2>
        <div class=\"table-scroll\"><table id=\"stock-table\"><thead><tr><th scope=\"col\">Ticker symbol</th><th scope=\"col\">Full company name</th><th scope=\"col\">Sector</th><th scope=\"col\">Market cap</th></tr></thead><tbody></tbody></table></div>
      </section>
    </section>
  </main>
  <div id=\"tooltip\" class=\"tooltip\" role=\"tooltip\" aria-hidden=\"true\"></div>
  <script src=\"js/d3.v6.min.js\"></script>
  <script src=\"js/visualization.js\"></script>
</body>
</html>
"""

CSS = """* { box-sizing: border-box; }
:root { color: #172033; background: #f4f7fb; font-family: Inter, system-ui, -apple-system, sans-serif; }
body { margin: 0; } .page { max-width: 1540px; margin: 0 auto; padding: 22px; }
h1 { margin: 0 0 4px; font-size: 1.7rem; } header p { margin: 0 0 20px; color: #56647a; }
#dashboard { display: flex; align-items: flex-start; gap: 20px; }
.panel { background: #fff; border: 1px solid #dce4ef; border-radius: 10px; box-shadow: 0 2px 8px #1720330c; padding: 14px; }
.chart-panel { flex: 1 1 58%; min-width: 570px; } .table-panel { flex: 1 1 42%; min-width: 420px; }
h2 { margin: 0 0 10px; font-size: 1.05rem; } #chart svg { display: block; width: 100%; height: auto; }
.legend { display: flex; flex-wrap: wrap; gap: 7px 14px; padding: 9px 3px 0; font-size: .78rem; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }.swatch { width: 12px; height: 12px; border-radius: 50%; border: 1px solid #ffffffaa; }
.bubble { stroke: #fff; stroke-width: 1.5px; cursor: pointer; transition: opacity .15s, stroke-width .15s; }.bubble.selected { stroke: #172033; stroke-width: 4px; }.bubble.dimmed { opacity: .42; }
.bubble-label { text-anchor: middle; dominant-baseline: central; pointer-events: none; fill: #fff; font-size: 10px; font-weight: 750; paint-order: stroke; stroke: #17203399; stroke-width: 2px; }
.cluster-name { font-size: 11px; fill: #62718a; text-anchor: middle; pointer-events: none; }
.table-scroll { max-height: 578px; overflow: auto; border: 1px solid #e1e7f0; border-radius: 6px; } table { border-collapse: collapse; width: 100%; font-size: .82rem; } th { position: sticky; top: 0; background: #edf2f8; z-index: 1; text-align: left; } th, td { padding: 8px 9px; border-bottom: 1px solid #e5ebf3; } td:last-child { text-align: right; font-variant-numeric: tabular-nums; } tbody tr { cursor: pointer; } tbody tr:hover { background: #f0f6ff; } tbody tr.selected { background: #ffe9a8; outline: 2px solid #d28c00; outline-offset: -2px; }
.tooltip { position: fixed; z-index: 10; max-width: 240px; padding: 9px 11px; color: white; background: #172033ed; border-radius: 6px; font-size: .82rem; line-height: 1.45; opacity: 0; transition: opacity .15s; pointer-events: none; white-space: pre-line; }.tooltip.visible { opacity: 1; }
.error { padding: 1rem; color: #991b1b; background: #fee2e2; border-radius: 6px; }
@media (max-width: 1050px) { #dashboard { flex-direction: column; } .chart-panel, .table-panel { width: 100%; min-width: 0; } }
"""

JS = r"""/* global d3 */
(() => {
  'use strict';
  const WIDTH = 720, HEIGHT = 560, DEFAULT_RADIUS = 17, PADDING = 3;
  const FIELD_ALIASES = {
    ticker: ['symbol', 'ticker', 'tickersymbol'],
    name: ['longname', 'name', 'fullname', 'companyname', 'shortname'],
    sector: ['sector', 'industrysector'],
    marketCap: ['marketcap', 'market_cap', 'marketcapitalization'],
    country: ['country'], website: ['website', 'url']
  };
  const key = s => String(s || '').trim().toLowerCase().replace(/[ _-]/g, '');
  const clean = value => String(value == null ? '' : value).trim();
  function get(row, aliases) {
    const map = new Map(Object.keys(row).map(k => [key(k), row[k]]));
    for (const alias of aliases) { const value = map.get(key(alias)); if (clean(value)) return clean(value); }
    return '';
  }
  function numberValue(value) {
    const text = clean(value).replace(/[$,\s]/g, '');
    if (!text) return null;
    const suffix = text.slice(-1).toUpperCase(), multipliers = {K: 1e3, M: 1e6, B: 1e9, T: 1e12};
    const amount = Number(suffix in multipliers ? text.slice(0, -1) : text);
    return Number.isFinite(amount) ? amount * (multipliers[suffix] || 1) : null;
  }
  function money(value) {
    if (!Number.isFinite(value)) return '—';
    const units = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']];
    for (const [limit, suffix] of units) if (Math.abs(value) >= limit) {
      const n = value / limit, digits = Math.abs(n) >= 100 ? 0 : Math.abs(n) >= 10 ? 1 : 2;
      return n.toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1') + suffix;
    }
    return String(Math.round(value));
  }
  function showError(message) { d3.select('#chart').append('p').attr('class', 'error').text(message); }
  if (typeof d3 === 'undefined') { showError('D3 v6 did not load. Confirm js/d3.v6.min.js is present.'); return; }

  d3.csv('data/stock-descriptions.csv').then(raw => {
    const seen = new Set();
    const data = raw.map((row, index) => {
      let ticker = get(row, FIELD_ALIASES.ticker) || `Record ${index + 1}`;
      if (seen.has(ticker)) ticker += ` (${index + 1})`; seen.add(ticker);
      const marketCap = numberValue(get(row, FIELD_ALIASES.marketCap));
      return { ticker, name: get(row, FIELD_ALIASES.name) || ticker, sector: get(row, FIELD_ALIASES.sector) || 'Unclassified', marketCap,
        country: get(row, FIELD_ALIASES.country), website: get(row, FIELD_ALIASES.website), source: row };
    });
    if (!data.length) throw new Error('The CSV contains no records.');
    render(data);
  }).catch(error => showError(`Could not load data/stock-descriptions.csv: ${error.message}. Serve this folder through HTTP rather than file://.`));

  function render(data) {
    const sectors = Array.from(new Set(data.map(d => d.sector))).sort(d3.ascending);
    const color = d3.scaleOrdinal().domain(sectors).range(d3.schemeTableau10.concat(d3.schemeSet3));
    const values = data.map(d => d.marketCap).filter(Number.isFinite);
    const radiusScale = d3.scaleSqrt().domain(d3.extent(values.length ? values : [0, 1])).range([12, 42]);
    data.forEach(d => { d.radius = Number.isFinite(d.marketCap) ? radiusScale(d.marketCap) : DEFAULT_RADIUS; });
    const cols = Math.ceil(Math.sqrt(sectors.length));
    const centers = new Map(sectors.map((sector, i) => [sector, { x: WIDTH * ((i % cols) + .5) / cols, y: HEIGHT * (Math.floor(i / cols) + .5) / Math.ceil(sectors.length / cols) }]));

    const svg = d3.select('#chart').append('svg').attr('viewBox', `0 0 ${WIDTH} ${HEIGHT}`).attr('role', 'img').attr('aria-label', 'Stocks grouped by sector; circle area indicates market capitalization.');
    svg.append('rect').attr('width', WIDTH).attr('height', HEIGHT).attr('rx', 6).attr('fill', '#f8fafc').attr('stroke', '#e0e7f0');
    svg.append('g').selectAll('text').data(sectors).join('text').attr('class', 'cluster-name').attr('x', s => centers.get(s).x).attr('y', s => centers.get(s).y - 60).text(s => s);
    const nodes = svg.append('g').attr('class', 'nodes').selectAll('g.node').data(data, d => d.ticker).join('g').attr('class', 'node').attr('tabindex', 0).attr('role', 'button').attr('aria-label', d => `Select ${d.ticker}`);
    const circles = nodes.append('circle').attr('class', 'bubble').attr('r', d => d.radius).attr('fill', d => color(d.sector));
    const labels = nodes.append('text').attr('class', 'bubble-label').text(d => d.ticker.length <= 7 ? d.ticker : '');
    const tooltip = d3.select('#tooltip');
    const canTooltip = d => Number.isFinite(d.marketCap) && !!d.country && !!d.website;
    function moveTooltip(event) { tooltip.style('left', `${event.clientX + 14}px`).style('top', `${event.clientY + 14}px`); }
    nodes.on('mouseenter', function(event, d) { if (!canTooltip(d)) return; tooltip.text(`${d.ticker}\n${d.name}\n${d.sector}`).classed('visible', true).attr('aria-hidden', 'false'); moveTooltip(event); })
      .on('mousemove', function(event, d) { if (canTooltip(d)) moveTooltip(event); })
      .on('mouseleave', () => tooltip.classed('visible', false).attr('aria-hidden', 'true'));

    const rows = d3.select('#stock-table tbody').selectAll('tr').data(data, d => d.ticker).join('tr').attr('data-ticker', d => d.ticker).attr('tabindex', 0).attr('role', 'button').attr('aria-label', d => `Select ${d.ticker}`);
    rows.each(function(d) { const row = d3.select(this); [d.ticker, d.name, d.sector, money(d.marketCap)].forEach(value => row.append('td').text(value)); });
    let selectedTicker = null;
    function select(d) {
      selectedTicker = d.ticker;
      circles.classed('selected', n => n.ticker === selectedTicker).classed('dimmed', n => n.ticker !== selectedTicker);
      rows.classed('selected', n => n.ticker === selectedTicker);
      const selectedRow = rows.filter(n => n.ticker === selectedTicker).node();
      if (selectedRow) selectedRow.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    nodes.on('click', (event, d) => select(d)).on('keydown', (event, d) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(d); } });
    rows.on('click', (event, d) => select(d)).on('keydown', (event, d) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(d); } });

    const simulation = d3.forceSimulation(data)
      .force('x', d3.forceX(d => centers.get(d.sector).x).strength(.16))
      .force('y', d3.forceY(d => centers.get(d.sector).y).strength(.16))
      .force('center', d3.forceCenter(WIDTH / 2, HEIGHT / 2))
      .force('collide', d3.forceCollide(d => d.radius + PADDING).strength(1).iterations(3))
      .force('charge', d3.forceManyBody().strength(-4))
      .force('boundsX', d3.forceX(d => Math.max(d.radius + 4, Math.min(WIDTH - d.radius - 4, d.x || WIDTH / 2))).strength(.025))
      .force('boundsY', d3.forceY(d => Math.max(d.radius + 4, Math.min(HEIGHT - d.radius - 4, d.y || HEIGHT / 2))).strength(.025))
      .on('tick', () => { data.forEach(d => { d.x = Math.max(d.radius + 3, Math.min(WIDTH - d.radius - 3, d.x)); d.y = Math.max(d.radius + 3, Math.min(HEIGHT - d.radius - 3, d.y)); }); nodes.attr('transform', d => `translate(${d.x},${d.y})`); });
    // Keep a reference for browser inspection and permit later data updates to restart it.
    window.stockBubbleSimulation = simulation;
    d3.select('#legend').selectAll('div.legend-item').data(sectors).join('div').attr('class', 'legend-item').each(function(sector) { const item = d3.select(this); item.append('span').attr('class', 'swatch').style('background-color', color(sector)); item.append('span').text(sector); });
  }
})();
"""

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def build(request):
    source = Path(request.get("source_root", "")).expanduser().resolve()
    output = Path(request.get("output_root", "")).expanduser().resolve()
    csv = source / "stock-descriptions.csv"
    if not csv.is_file():
        raise ValueError(f"source_root must contain stock-descriptions.csv: {csv}")
    output.mkdir(parents=True, exist_ok=True)
    destination_data = output / "data"
    if destination_data.exists(): shutil.rmtree(destination_data)
    shutil.copytree(source, destination_data)
    d3_path = output / "js" / "d3.v6.min.js"
    # Some execution gateways reject urllib's default Python user agent at d3js.org.
    # Use a normal request header and try independent v6 mirrors before failing.
    requested_url = request.get("d3_url")
    urls = (requested_url,) if requested_url else (DEFAULT_D3_URL,) + D3_FALLBACK_URLS
    errors, d3_source = [], None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; stock-app-generator/1.0)", "Accept": "application/javascript,text/javascript,*/*;q=0.8"})
            with urllib.request.urlopen(req, timeout=60) as response:
                candidate = response.read()
            if len(candidate) < 100000 or b"d3" not in candidate.lower():
                raise ValueError("download was not a complete D3 distribution")
            d3_source = candidate
            break
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    if d3_source is None:
        raise RuntimeError("could not obtain the required local D3 v6 library: " + "; ".join(errors))
    d3_path.parent.mkdir(parents=True, exist_ok=True)
    d3_path.write_bytes(d3_source)
    write(output / "index.html", HTML)
    write(output / "css" / "style.css", CSS)
    write(output / "js" / "visualization.js", JS)
    required = [output / "index.html", d3_path, output / "js" / "visualization.js", output / "css" / "style.css", destination_data / "stock-descriptions.csv"]
    missing = [str(p) for p in required if not p.is_file() or p.stat().st_size == 0]
    if missing: raise RuntimeError("generation validation failed for: " + ", ".join(missing))
    return {"ok": True, "output_root": str(output), "files": [str(p.relative_to(output)) for p in required]}

def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict): raise ValueError("stdin must contain a JSON object")
        print(json.dumps(build(request)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
if __name__ == "__main__": main()
