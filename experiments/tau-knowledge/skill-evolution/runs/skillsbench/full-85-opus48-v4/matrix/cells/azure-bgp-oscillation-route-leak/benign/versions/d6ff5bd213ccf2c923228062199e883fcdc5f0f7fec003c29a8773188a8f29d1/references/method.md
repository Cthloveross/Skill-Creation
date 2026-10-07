# Analysis method and data-format notes

## 1. Oscillation detection (preference dependency cycle)
- Build a directed graph from `preferences.json`: an edge `u -> v` means AS `u`
  currently prefers a route via AS `v`. Entries look like `{as: {prefer_via: v}}`.
- A persistent BGP oscillation exists iff this preference graph contains a
  directed cycle. Detect it with a colour-based DFS (`find_cycle`).
- `oscillation_cycle` and `affected_ases` are the sorted unique AS numbers on
  the detected cycle. Do not infer a cycle from hub names or from a generic
  description of a mechanism; it must be present in the runtime preferences.

## 2. Route-leak detection (valley-free export model)
- Runtime advertisements come from `route_events.json` (NOT `route.json`, which
  only carries the advertised prefix/origin). Each event has `advertiser_asn`
  (leaker), `source_asn`, `destination_asn`, `source_type`, `destination_type`.
- For each advertisement determine two relationships:
  - `source_type`: how the leaker *learned* the route (customer/peer/provider).
  - `destination_type`: the relationship on which it is *exported*.
  If an event omits a type, fill it from `relationships.json`.
- Valley-free rule: customer-learned routes may be exported to any neighbour;
  peer-learned and provider-learned routes may be exported **only to
  customers**.
- A route leak is therefore any advertisement where `source_type` is `peer` or
  `provider` and `destination_type` is not `customer`. In this Azure Virtual WAN
  scenario it is concretely hub1 (65002) re-advertising a provider (Virtual WAN,
  65001) route to peer hub2 (65003).
- `local_pref.json` maps relationship types to local-preference weights
  (context); the leak test itself is the learned/exported combination above.

## 3. Solution evaluation (simulate the stated mechanism, do not label)
For every entry in `possible_solutions.json`:
1. Determine the solution's **stated mechanism** only. Prefer a structured
   `effects` object (`remove_pref_edges`, `block_advertisements`,
   `breaks_cycle`, `stops_route_leak`). If none exists, map the description to
   graph edits by recognising the mechanism:
   - **Breaks the preference cycle** (-> remove the detected cycle edges):
     updating a hub to stop preferring the other hub ("stop preferring",
     "no longer prefer"); a preference hierarchy that deprioritises the peer
     hub; disabling/removing the hub-to-hub peering; routing-intent / forcing
     hub-to-hub traffic through the Virtual WAN only.
   - **Stops the leak** (-> block the leaking advertisements): an export policy
     or no-export community that blocks announcing provider routes to the peer
     hub; disabling the peering; routing-intent via the Virtual WAN only.
   - **Changes nothing** (resolves neither): keepalive/holdtime timers, route
     dampening, ECMP, prefix limits, BGP session restart, "wait for
     convergence", RPKI origin validation (origin is valid), generic route
     maps, forwarding/next-hop overrides, inbound *accept* filters, *ingress*
     filtering on the receiving hub, and export filters targeting the wrong
     routes (e.g. routes learned from the peer rather than the leaked provider
     routes). Note: generic route-selection tweaks (shorter AS-PATH / MED) are
     NOT treated as breaking the mutual preference unless they explicitly stop
     preferring the other hub.
2. Apply those edits to **copies** of the preference and advertisement graphs.
3. Re-run both analyses on the copies.
   - `oscillation_resolved` = a cycle existed before AND no cycle remains after.
   - `route_leak_resolved` = a leak existed before AND no leaking advertisement
     remains after.

A label such as "fixes oscillation" is not evidence; only the absence of the
cycle or the invalid export after applying the stated mechanism counts.

## 4. Expected input field names (verify against generate_data.py)
The parser accepts several conventions. Confirm the real ones:
- `preferences.json`: dict `{as: {prefer_via: v}}` / `{as: [prefs]}`, or a list
  of `{from,to}` / `{source,preferred}` / `[u,v]` pairs.
- `route_events.json`: list of advertisement events with
  `advertiser_asn`/`source_asn`/`destination_asn`/`source_type`/`destination_type`
  (also accepts `leaker_as`/`source_as`/`destination_as` etc.). `route.json` is
  used only as a fallback advertisement source.
- `relationships.json`: list of `{from,to,type}` AS relationships.
- `local_pref.json`: relationship-type -> weight mapping.
- `possible_solutions.json`: list of strings, list of `{description, effects}`
  dicts, or a dict keyed by description.

If the generator uses other names, extend `extract_pref_edges`,
`extract_advertisements`, `collect_relationships`, `extract_solutions`,
`build_modifications`, or the `norm_rel` synonyms in `scripts/analyze.py`.
Keep the fix in the reusable script; never paste this instance's answers.
