---
name: azure-bgp-oscillation-route-leak
description: Analyze runtime BGP route, preference, relationship-weight, and solution JSON files for actual preference cycles and valley-free export violations, then write the required Azure Virtual WAN oscillation report. Use when a task supplies route.json, preferences.json, local_pref.json, and possible_solutions.json.
---

# Azure BGP oscillation and route-leak analysis

Use `scripts/analyze_bgp.py` to create `/app/output/oscillation_report.json` from the runtime data. The helper uses only the Python standard library and discovers common JSON layouts rather than assuming a fixed export schema.

## Required inputs

The data directory must contain JSON files named (case-insensitively) `route.json`, `preferences.json`, `local_pref.json`, and `possible_solutions.json`. By default the script reads `/app/data`. It falls back to `/app/environment/data` only when that directory itself contains all four required files.

The task setup may provide a generator separately. If the required four files are absent, inspect the supplied setup/generator documentation and run the task-provided generator as appropriate before analyzing; do not treat ARM deployment templates or an architecture image as route-policy evidence.

## Run

```bash
mkdir -p /app/output
python3 scripts/analyze_bgp.py <<'JSON'
{"data_dir":"/app/data","output_path":"/app/output/oscillation_report.json"}
JSON
```

The script receives one JSON object on stdin and emits a compact JSON summary on stdout. Input fields are:

- `data_dir` (optional string): directory containing the four input JSON files; default `/app/data`.
- `output_path` (optional string): report destination; default `/app/output/oscillation_report.json`.

It exits nonzero with a JSON error on stderr if a required input cannot be found or parsed. Its stdout summary includes the output path and detected counts; the report itself is the task artifact.

## Method and interpretation

1. Inspect the output report's source data if the script reports no recognized preference edges or advertisements. Schema inference is deliberately evidence-based: AS identifiers can be JSON numbers, numeric strings, or `AS...` strings, and records may be nested.
2. Oscillation is `true` only if the directed runtime preference graph has an actual directed cycle. `oscillation_cycle` and `affected_ases` contain a deterministic representative cycle without duplicating its closing AS.
3. A route leak is emitted only for an advertisement whose learned/source relationship is `provider` or `peer` and whose export/destination relationship is not `customer`. The output preserves the advertising (leaker), route source, export destination, and both relationship types.
4. Every solution is evaluated on copied graph/list state. Explicit structured effects (removed preferences, replacements, removed advertisements, or explicit stop/break flags) are applied. Text effects are recognized only when they explicitly state that they break a preference cycle or stop/filter/deny route advertising/propagation. Timer, monitoring, and forwarding-only changes do not alter policy state.
5. A solution resolves oscillation only when the post-change graph has no cycle. It resolves route leaks only when no invalid advertisement remains. Do not equate a solution name with a successful policy change.

## Validation

Confirm that `/app/output/oscillation_report.json` exists and parses as JSON. It must contain boolean `oscillation_detected` and `route_leak_detected`, arrays `oscillation_cycle`, `affected_ases`, and `route_leaks`, and an object `solution_results`. Each leak must have numeric AS fields plus string `source_type` and `destination_type`; each solution result must contain boolean `oscillation_resolved` and `route_leak_resolved`.
