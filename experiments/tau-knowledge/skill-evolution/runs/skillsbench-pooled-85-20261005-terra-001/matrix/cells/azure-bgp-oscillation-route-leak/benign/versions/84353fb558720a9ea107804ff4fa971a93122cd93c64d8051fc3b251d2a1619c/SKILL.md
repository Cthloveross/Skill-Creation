---
name: azure-bgp-oscillation-route-leak
description: Generate and analyze runtime Azure Virtual WAN BGP data to detect actual preference-cycle oscillations and valley-free route leaks, evaluate every supplied mitigation, and write /app/output/oscillation_report.json.
---

# Azure BGP oscillation and route-leak analysis

Use the task-supplied data generator before analysis when it is present. The deployment template and image are not policy evidence; the generator materializes the runtime JSON inputs used for the report.

## Prepare and run

```bash
mkdir -p /app/data /app/output
if [ -f /app/environment/generate_data.py ]; then
  python3 /app/environment/generate_data.py
fi
python3 scripts/analyze_bgp.py <<'JSON'
{"data_dir":"/app/data","output_path":"/app/output/oscillation_report.json"}
JSON
```

The analyzer reads JSON from stdin and writes a compact JSON execution summary to stdout. Its input is an object with:

- `data_dir` (optional string, default `/app/data`): directory containing `route.json`, `preferences.json`, `local_pref.json`, and `possible_solutions.json`; `topology.json`, `relationships.json`, and `route_events.json` are used when available.
- `output_path` (optional string, default `/app/output/oscillation_report.json`): required report artifact path.

It exits nonzero with a JSON error on stderr when required input JSON is missing or invalid.

## Analysis rules

The script discovers nested JSON records and normalizes numeric and `AS...` ASN representations. It resolves hub labels in preference policies through topology ASNs before building directed preference edges. Oscillation is reported only when those runtime edges have a directed cycle. The report uses the complete set of ASNs participating in directed cycles, so `oscillation_cycle` and `affected_ases` agree and contain numeric ASNs.

A route leak requires a route learned from a `peer` or `provider` to be exported to a non-`customer`, under valley-free export rules. The script reports only fully identified, runtime-grounded advertisements.

Every discoverable solution identifier in `possible_solutions.json` receives an entry, including when the base topology has no issue. Each solution is simulated against copied preference and advertisement state. Explicit edge/removal/replacement/filter effects and clearly stated policy effects are applied; timer, monitoring, and forwarding-only changes do not alter BGP policy. A resolution boolean is true only when the corresponding post-change cycle or invalid export is absent.

## Validate

Confirm `/app/output/oscillation_report.json` parses as a JSON object with these fields:

- boolean `oscillation_detected` and `route_leak_detected`;
- integer-ASN arrays `oscillation_cycle` and `affected_ases`;
- array `route_leaks`, whose members have numeric `leaker_as`, `source_as`, `destination_as` and nonempty relationship strings; and
- object `solution_results`, containing every supplied solution and exactly boolean `oscillation_resolved` and `route_leak_resolved` for each.
