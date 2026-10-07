---
name: azure-bgp-oscillation-route-leak
description: Analyze supplied BGP JSON exports for preference cycles and valley-free route leaks, assess explicit policy interventions, and write the Azure Virtual WAN oscillation report. Use when route, preference, relationship/local-preference, route-event, and candidate-solution JSON files are available.
---

# BGP oscillation and route-leak analysis

Use the supplied runtime JSON as the source of truth. Do not infer routing relationships or solution effects solely from hub names, diagrams, or product terminology.

## Inputs and output

The required files in `/app/data` are `route.json`, `preferences.json`, `local_pref.json`, and `possible_solutions.json`. Deployments may put concrete advertisements in `route.json` or in a sidecar such as `route_events.json`; the analyzer inspects JSON sidecars for explicitly attributed advertisement records. Relationship sidecars can supply context but do not by themselves establish an advertisement.

Run:

```sh
python3 /app/environment/skills/current/scripts/analyze_bgp.py \
  --data-dir /app/data --output /app/output/oscillation_report.json
python3 -m json.tool /app/output/oscillation_report.json
```

Alternatively, pass `{"data_dir":"...","output":"..."}` on stdin. The script writes the same report to the requested path and emits it on stdout. The report contains booleans `oscillation_detected` and `route_leak_detected`; numeric arrays `oscillation_cycle` and `affected_ases`; a `route_leaks` array of objects with `leaker_as`, `source_as`, `destination_as`, `source_type`, and `destination_type`; and `solution_results`, keyed by every supplied solution, with boolean `oscillation_resolved` and `route_leak_resolved` fields.

## Method

1. Parse the preference export into a directed graph whose edge is `(AS choosing a route, AS used as next hop)`. The script supports both record lists and ASN-keyed mappings containing `prefer_via`. Report only a real directed cycle, without repeating its starting ASN.
2. Extract only records that explicitly identify advertiser, source, destination, and the inbound/outbound relationship. A provider- or peer-learned route exported to anything other than a customer violates valley-free export. Do not call a topology relationship or an origin route alone a leak.
3. For each intervention, apply its stated effect to copies of the preference and advertisement findings. Explicit preference removal, peer-adjacency removal, or an explicit replacement hierarchy can break a cycle. Explicit no-export, export blocking, or a matching import rejection can remove the affected advertisement. Timers, monitoring, forwarding overrides, generic route maps, and unrelated validation do not change either policy graph merely by name.
4. Verify that every solution label occurs in `solution_results`, ASNs are JSON numbers, all arrays remain arrays, and the saved document parses as JSON.

## Limits and failure handling

The analyzer exits nonzero for a missing required file or invalid JSON. If a new export encodes preferences or advertisements under unrecognized field names, inspect the runtime records and add a schema alias plus a small representative test; do not guess the direction of an edge. If a prose intervention does not state a policy effect, report it as not resolving the relevant finding rather than assuming that it does.
