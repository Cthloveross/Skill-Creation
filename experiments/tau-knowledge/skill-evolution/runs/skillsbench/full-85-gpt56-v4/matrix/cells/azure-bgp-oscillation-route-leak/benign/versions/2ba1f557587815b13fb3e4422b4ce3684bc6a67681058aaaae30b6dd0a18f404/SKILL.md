---
name: azure-bgp-oscillation-route-leak
description: Analyze runtime JSON exports for BGP preference cycles and valley-free route leaks, then assess stated routing interventions and write the required Azure Virtual WAN oscillation report. Use when route, preference, relationship-weight, and possible-solution JSON files are supplied.
---

# BGP oscillation and route-leak analysis

Use this Skill for the Azure Virtual WAN task. The source data is authoritative: do not infer topology, relationships, or solution effects from hub names, a diagram, or a generic BGP configuration.

## Inputs and output

The task normally supplies these files under `/app/data`:

- `route.json` — advertised route records;
- `preferences.json` — directed route-preference dependencies;
- `local_pref.json` — relationship labels and/or their preference weights;
- `possible_solutions.json` — candidate interventions.

Run the packaged analyzer (it discovers ordinary JSON container shapes and key spelling variants):

```sh
python3 /app/environment/skills/current/scripts/analyze_bgp.py \
  --data-dir /app/data --output /app/output/oscillation_report.json
```

The script also accepts a JSON object on stdin with optional `data_dir` and `output` fields and emits the report JSON on stdout. Its normal output schema is exactly:

- `oscillation_detected`: boolean;
- `oscillation_cycle`: array of AS numbers (empty if absent);
- `affected_ases`: array of AS numbers (empty if absent);
- `route_leak_detected`: boolean;
- `route_leaks`: array of objects with `leaker_as`, `source_as`, `destination_as`, `source_type`, and `destination_type`;
- `solution_results`: object keyed by each supplied solution label, whose values contain booleans `oscillation_resolved` and `route_leak_resolved`.

## Method

1. Inspect the actual files, especially `generate_data.py` if present beside the supplied data, before interpreting ambiguous fields. Confirm whether an edge means “AS prefers a route through AS” or the reverse. The analyzer defaults to the explicit source/target direction and supports direction metadata such as `from`/`to`.
2. Construct the directed preference graph and find actual directed cycles. A self-loop is a cycle. Only report an ordered cycle actually present in that graph; the script canonicalizes its start for stable JSON.
3. For every advertisement, identify the AS that learned/re-advertises it, the upstream/source AS, outgoing/destination AS, and the relationship on both sides. A route learned from a provider or peer may be exported only to a customer. Flag every record that has a provider/peer source relationship and a non-customer destination relationship. Preserve the record-derived types in the report.
4. Assess every solution by its structured effect when available (removed/added preference edges, changed relationship/export policy, explicit booleans). Recompute cycle and leak conditions on copies after those effects. For prose-only candidates, classify only explicit route filtering/export blocking as stopping a leak and only explicit preference/adjacency removal or cycle-breaking as breaking a cycle. Timers, monitoring, forwarding-only changes, and labels alone do not fix either policy defect.
5. Validate the saved file with `python3 -m json.tool /app/output/oscillation_report.json`. Ensure all supplied solutions appear as keys, ASNs are JSON numbers, and arrays remain arrays even when empty.

## Ambiguity and failures

If input uses a schema the generic extractor cannot identify, inspect its records and extend the aliases in `scripts/analyze_bgp.py` rather than guessing an answer. Do not claim a route leak merely because a route traverses Virtual WAN: both learned and export relationships are required. Do not mark a solution resolved merely because it mentions BGP or Azure. The analyzer exits with a clear error if required named input files are absent or invalid JSON.
