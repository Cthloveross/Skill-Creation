---
name: azure-bgp-oscillation-route-leak
description: >-
  Detect BGP route oscillation (preference dependency cycle) and valley-free
  route leaks in an Azure Virtual WAN topology from JSON inputs, then evaluate
  which proposed solutions actually resolve each defect by simulating their
  stated effects on copies of the preference/advertisement graphs. Use when a
  task supplies route.json, preferences.json, local_pref.json and
  possible_solutions.json and asks for an oscillation_report.json verdict.
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

## Method (do not infer defects from names)
Follow `references/method.md`. Core principles from the frozen background:

1. **Oscillation = preference dependency cycle.** Model routing preferences as a
   directed graph (edge `u -> v` means AS `u` currently prefers a route via
   `v`). A persistent oscillation exists iff this graph has a directed cycle.
   `oscillation_cycle`/`affected_ases` are the AS numbers on that cycle.
2. **Route leak = valley-free export violation.** For every runtime
   advertisement combine the relationship the route was *learned* on with the
   relationship it is *exported* on. Customer-learned routes may be exported to
   any neighbor; peer/provider-learned routes may be exported **only to
   customers**. A route leak is a route learned from a peer/provider and
   exported to a non-customer (peer or provider). In this VWAN task the concrete
   case is hub1/hub2 re-advertising a route to the other hub via Virtual WAN.
3. **Evaluate each solution by simulation, not by its label.** Apply only the
   solution's *stated effects* to a **copy** of the preference and advertisement
   graphs, then re-run both analyses. `oscillation_resolved` is true only if a
   cycle existed before and no cycle remains after. `route_leak_resolved` is
   true only if a leak existed before and no leaking advertisement remains after.
   Timer/keepalive/holdtime changes, monitoring, logging and forwarding
   overrides change neither the preference cycle nor the invalid export, so they
   resolve neither unless their stated effect actually removes an edge or an
   advertisement.

## How to run
Inputs normally live in `/app/data/`. If that directory does not yet contain the
JSON inputs, generate them first (the generator is shipped with the task):

```bash
ls /app/data || python /app/environment/generate_data.py
```

Then run the analyzer. It reads a small JSON config on stdin and prints a JSON
result on stdout, and also writes the report file:

```bash
echo '{"data_dir": "/app/data", "output_path": "/app/output/oscillation_report.json"}' \
  | python /app/environment/skills/current/scripts/analyze.py
```

With empty/absent config it defaults to `data_dir=/app/data` (falling back to
`/app/environment/data`) and `output_path=/app/output/oscillation_report.json`.

The stdout JSON is `{"status":..., "output_path":..., "report":{...},
"diagnostics":{...}}`. `diagnostics` lists the parsed preference edges,
advertisements, relationships and solution names so you can confirm the inputs
were understood.

## Verify before trusting the output
Because the exact field names in the generated JSON are not fixed, **always**
inspect the real inputs and the generator, then confirm the parse:

```bash
head -c 4000 /app/environment/generate_data.py
for f in route preferences local_pref possible_solutions; do echo "== $f =="; cat /app/data/$f.json; done
python /app/environment/skills/current/scripts/analyze.py < /dev/null | python -m json.tool | head -n 120
```

Checklist:
- `diagnostics.pref_edges` reflects the real preference pairs and the detected
  `oscillation_cycle` matches a genuine directed cycle in them.
- `diagnostics.advertisements` carries each advertisement with normalized
  `source_type`/`destination_type`; every entry in `route_leaks` is a
  peer/provider-learned route exported to a non-customer.
- `solution_results` has one key per solution (keyed by its description string),
  and each resolved flag follows from the re-run analysis, not the wording.

If the generator uses field names the parser does not recognise, extend the
extraction helpers in `scripts/analyze.py` (`extract_pref_edges`,
`extract_advertisements`, `extract_solutions`, `build_modifications`) and/or the
relationship synonyms in `norm_rel` so the real schema maps onto the model.
Prefer a targeted parsing fix over hardcoding this instance's answers.

## Failure handling
- Missing input file: the analyzer records it under `diagnostics.missing` and
  still writes a well-formed report with the fields it can compute. Generate or
  locate the input, then rerun.
- No cycle / no leak found: `*_detected` is false and the corresponding
  `*_resolved` flags are false for every solution (nothing to resolve).
- Unparseable solution effects: the parser falls back to documented keyword
  heuristics that are translated into graph modifications and re-simulated;
  verify these against the real solution text and refine if needed.
