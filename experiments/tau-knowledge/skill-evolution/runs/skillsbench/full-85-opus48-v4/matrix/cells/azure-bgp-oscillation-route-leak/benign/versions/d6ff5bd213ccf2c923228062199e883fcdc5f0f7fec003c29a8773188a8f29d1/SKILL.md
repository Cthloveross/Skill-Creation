---
name: azure-bgp-oscillation-route-leak
description: >-
  Detect BGP route oscillation (preference dependency cycle) and valley-free
  route leaks in an Azure Virtual WAN topology from JSON inputs, then evaluate
  which proposed solutions actually resolve each defect by simulating their
  stated mechanisms on copies of the preference/advertisement graphs. Use when
  a task supplies route/preferences/local_pref inputs (plus route_events and
  relationships) and a possible_solutions list and asks for an
  oscillation_report.json verdict.
---

# Azure BGP oscillation & route-leak analyzer

## What this Skill produces
A single JSON file at `/app/output/oscillation_report.json` with the exact shape
required by the task:

```json
{
  "oscillation_detected": true,
  "oscillation_cycle": [65002, 65003],
  "affected_ases": [65002, 65003],
  "route_leak_detected": true,
  "route_leaks": [{"leaker_as":65002,"source_as":65001,"destination_as":65003,"source_type":"provider","destination_type":"peer"}],
  "solution_results": {"<solution description>": {"oscillation_resolved": false, "route_leak_resolved": true}}
}
```
`solution_results` has one key per solution (its description string).

## Inputs (in `/app/data/`)
- `preferences.json` — routing preferences. Mapping of AS -> `{prefer_via: <AS>}`
  (or list of edges). Each entry is a directed preference edge `AS -> prefer_via`.
- `route.json` — the advertised prefix / origin ASN (context, not the leak event).
- `route_events.json` — the actual runtime advertisements/leak events, each with
  `advertiser_asn`, `source_asn`, `destination_asn`, `source_type`,
  `destination_type`. **This is where route leaks are observed**, not `route.json`.
- `relationships.json` — AS relationships (`from`, `to`, `type`) used to fill in
  missing learned/exported types when an advertisement omits them.
- `local_pref.json` — relationship weight table (context).
- `possible_solutions.json` — list of candidate solution strings to evaluate.
- `topology.json` — physical adjacencies (context).

## Method (do not infer defects from names)
Follow `references/method.md`. Core principles from the frozen background:

1. **Oscillation = preference dependency cycle.** Model routing preferences as a
   directed graph (edge `u -> v` means AS `u` currently prefers a route via
   `v`). A persistent oscillation exists iff this graph has a directed cycle.
   `oscillation_cycle`/`affected_ases` are the sorted AS numbers on that cycle.
2. **Route leak = valley-free export violation.** For every runtime
   advertisement (from `route_events.json`) combine the relationship the route
   was *learned* on (`source_type`) with the relationship it is *exported* on
   (`destination_type`). Customer-learned routes may be exported to any
   neighbor; peer/provider-learned routes may be exported **only to customers**.
   A leak is a peer/provider-learned route exported to a non-customer — here a
   hub re-advertising a provider (Virtual WAN) route to the other hub (a peer).
3. **Evaluate each solution by simulating its stated mechanism.** Translate the
   solution's described effect into concrete edits on a **copy** of the graphs,
   then re-run both analyses:
   - A solution resolves oscillation only if its mechanism removes a preference
     edge on the detected cycle (e.g. a hub updated to stop preferring the other
     hub, a preference hierarchy that deprioritises the peer hub, disabling the
     hub-to-hub peering, or routing-intent forcing hub-to-hub traffic through the
     Virtual WAN only) — i.e. no cycle remains afterward.
   - A solution resolves a route leak only if its mechanism stops the offending
     advertisement at the leaker (an export policy / no-export community that
     blocks announcing provider routes to the peer hub, disabling the peering,
     or routing-intent via the Virtual WAN only) — i.e. no leaking advertisement
     remains afterward.
   - Timers/keepalive/holdtime, route dampening, ECMP, prefix limits, session
     restarts, "wait for convergence", RPKI origin validation (origin is valid),
     generic route maps, forwarding/next-hop overrides, inbound accept filters,
     ingress filtering on the *receiving* hub, and export filters that target the
     *wrong* routes (e.g. routes learned from the peer rather than the leaked
     provider routes) change neither the preference cycle nor the invalid export,
     so they resolve neither.

## How to run
```bash
ls /app/data || python /app/environment/generate_data.py   # ensure inputs exist
echo '{"data_dir": "/app/data", "output_path": "/app/output/oscillation_report.json"}' \
  | python /app/environment/skills/current/scripts/analyze.py
```
With empty/absent config it defaults to `data_dir=/app/data` (falling back to
`/app/environment/data`) and `output_path=/app/output/oscillation_report.json`.

The stdout JSON is `{"status":..., "output_path":..., "report":{...},
"diagnostics":{...}}`. `diagnostics` lists `pref_edges`, `detected_cycle`,
`advertisements`, `relationships` and `solution_names` so you can confirm the
inputs were understood. The report is also written to `output_path`.

## Verify before trusting the output
```bash
for f in route preferences local_pref possible_solutions route_events relationships; do \
  echo "== $f =="; cat /app/data/$f.json 2>/dev/null; done
python /work/candidate/scripts/analyze.py < /dev/null | python -m json.tool | head -n 60
```
Checklist:
- `diagnostics.pref_edges` reflects the real `prefer_via` pairs and the detected
  cycle matches a genuine directed cycle in them.
- `diagnostics.advertisements` carries each advertisement with normalized
  `source_type`/`destination_type`; every `route_leaks` entry is a
  peer/provider-learned route exported to a non-customer.
- `solution_results` has one key per solution, and each resolved flag follows
  from the re-run analysis (mechanism translated to graph edit), not the wording.

If the generator uses field names the parser does not recognise, extend the
extraction helpers in `scripts/analyze.py` (`extract_pref_edges`,
`extract_advertisements`, `extract_solutions`, `build_modifications`, the
relationship synonyms in `norm_rel`, or the mechanism keywords in
`build_modifications`). Prefer a targeted parsing fix over hardcoding answers.

## Failure handling
- Missing required input: recorded under `diagnostics.missing`; the analyzer
  still writes a well-formed report with the fields it can compute. Generate or
  locate the input, then rerun. `route_events.json`/`relationships.json`/
  `topology.json` are optional and silently skipped if absent.
- No cycle / no leak found: `*_detected` is false and every `*_resolved` flag is
  false (nothing to resolve).
- Solutions carrying a structured `effects` object are honoured directly;
  otherwise the described mechanism is recognised by keyword and re-simulated.
  Verify these against the real solution text and refine if needed.
