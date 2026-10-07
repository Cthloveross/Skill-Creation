# Analysis method and data-format notes

## 1. Oscillation detection (preference dependency cycle)
- Build a directed graph from `preferences.json`: an edge `u -> v` means AS `u`
  currently prefers a route via AS `v`.
- A persistent BGP oscillation exists iff this preference graph contains a
  directed cycle. Detect it with a colour-based DFS (`find_cycle`).
- `oscillation_cycle` and `affected_ases` are the sorted unique AS numbers on
  the detected cycle. Do not infer a cycle from hub names or from a generic
  description of a mechanism; it must be present in the runtime preferences.

## 2. Route-leak detection (valley-free export model)
- For each runtime advertisement determine two relationships:
  - `source_type`: how the leaker *learned* the route (customer/peer/provider).
  - `destination_type`: the relationship on which it is *exported*.
- Valley-free rule: customer-learned routes may be exported to any neighbour;
  peer-learned and provider-learned routes may be exported **only to
  customers**.
- A route leak is therefore any advertisement where `source_type` is `peer` or
  `provider` and `destination_type` is not `customer`. In the Azure Virtual WAN
  scenario this is concretely hub1/hub2 re-advertising a route to the other hub
  via Virtual WAN.
- `local_pref.json` maps relationship types to local-preference weights; it can
  help label relationships but the leak test itself is the learned/exported
  combination above.

## 3. Solution evaluation (simulate, do not label)
For every entry in `possible_solutions.json`:
1. Determine the solution's **stated effects** only. Prefer a structured
   `effects` object (e.g. `remove_pref_edges`, `block_advertisements`,
   `breaks_cycle`, `stops_route_leak`). If none exists, map the description text
   to modifications via documented keyword heuristics:
   - preference-changing wording (local-pref, AS-path prepend, weight, MED,
     routing preference) -> removes a cycle edge;
   - advertisement-stopping wording (branch-to-branch disable, route filter,
     prefix list, routing intent, deny community) -> blocks the leaking
     advertisements;
   - timer/keepalive/holdtime, monitoring, logging, alerting -> change nothing
     in the preference graph or the export set.
2. Apply those modifications to **copies** of the preference and advertisement
   graphs.
3. Re-run both analyses on the copies.
   - `oscillation_resolved` = a cycle existed before AND no cycle remains after.
   - `route_leak_resolved` = a leak existed before AND no leaking advertisement
     remains after.

A label such as "fixes oscillation" is not evidence; only the absence of the
cycle or the invalid export after applying the stated effects counts.

## 4. Expected input field names (verify against generate_data.py)
The parser accepts several conventions. Confirm the real ones:
- `preferences.json`: dict `{as: pref}` / `{as: [prefs]}`, or a list of
  `{from,to}` / `{source,preferred}` / `[u,v]` pairs.
- `route.json`: a list under `advertisements`/`ads`/`exports`/`route_leaks`,
  each with leaker/source/destination AS and (optionally) learned/export types;
  relationships may also appear under `relationships`/`topology`/`links`.
- `local_pref.json`: relationship-type -> weight mapping.
- `possible_solutions.json`: list of strings, list of `{description, effects}`
  dicts, or a dict keyed by description.

If the generator uses other names, extend `extract_pref_edges`,
`extract_advertisements`, `collect_relationships`, `extract_solutions`,
`build_modifications`, or the `norm_rel` synonyms in `scripts/analyze.py`.
Keep the fix in the reusable script; never paste this instance's answers.
