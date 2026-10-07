#!/usr/bin/env python3
"""Analyze BGP preference and advertisement JSON exports.

CLI: --data-dir DIR --output FILE.  A JSON stdin object may override these with
{"data_dir": ..., "output": ...}.  The report is emitted as JSON on stdout.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def nk(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def asn(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"\s*\d+\s*", value):
        return int(value)
    if isinstance(value, dict):
        return first_asn(value, ("asn", "as", "number", "id"))
    return None


def lookup(record, names):
    if not isinstance(record, dict):
        return None
    normalized = {nk(key): value for key, value in record.items()}
    for name in names:
        if nk(name) in normalized:
            return normalized[nk(name)]
    return None


def first_asn(record, names):
    return asn(lookup(record, names))


def relation(value):
    if isinstance(value, dict):
        value = lookup(value, ("type", "relationship", "role", "name"))
    text = nk(value or "")
    if "customer" in text or text in {"cust", "c"}:
        return "customer"
    if "provider" in text or "transit" in text or text in {"provider", "prov", "p"}:
        return "provider"
    if "peer" in text:
        return "peer"
    return str(value).lower() if value is not None else "unknown"


def walk(value):
    """Yield every mapping below a JSON value without assuming its container."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON in %s: %s" % (path, exc))


def required(directory, name):
    path = directory / name
    if not path.is_file():
        matches = list(directory.rglob(name))
        if not matches:
            raise FileNotFoundError("missing required input " + str(path))
        return matches[0]
    return path


def preference_edges(data):
    """Return directed (chooser, next-hop) preference dependencies."""
    edges = set()
    # Typical exports can be {65002: {"prefer_via": 65003}}.  The map key is
    # meaningful, so inspect it before recursively examining the child mapping.
    if isinstance(data, dict):
        for key, value in data.items():
            left = asn(key)
            if left is not None and isinstance(value, dict):
                right = first_asn(value, ("prefer_via", "preferred_via", "next_hop_as", "via_as", "to_as", "to"))
                if right is not None:
                    edges.add((left, right))
    for record in walk(data):
        keys = {nk(key) for key in record}
        left = first_asn(record, ("from_as", "fromasn", "source_as", "sourceasn", "asn", "as"))
        right = first_asn(record, ("prefer_via", "preferred_via", "next_hop_as", "via_as", "to_as", "to", "destination_as"))
        preference_words = any("prefer" in key or "localpref" in key or "routingpreference" in key for key in keys)
        if left is not None and right is not None and preference_words:
            edges.add((left, right))
    return edges


def cycle(edges):
    graph = {}
    for left, right in edges:
        graph.setdefault(left, set()).add(right)
    state, stack = {}, []
    def visit(node):
        state[node] = 1
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):]
            if state.get(nxt, 0) == 0:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return []
    for node in sorted(graph):
        if state.get(node, 0) == 0:
            found = visit(node)
            if found:
                start = min(range(len(found)), key=found.__getitem__)
                return found[start:] + found[:start]
    return []


def advertisements(all_data):
    """Find explicit export events in route exports and optional event sidecars."""
    found, seen = [], set()
    for data in all_data:
        for record in walk(data):
            source = first_asn(record, ("source_as", "sourceasn", "source_asn", "learned_from_as", "upstream_as", "origin_as"))
            destination = first_asn(record, ("destination_as", "destinationasn", "destination_asn", "advertised_to_as", "export_to_as", "to_as"))
            leaker = first_asn(record, ("leaker_as", "advertiser_as", "advertiser_asn", "exporter_as", "hub_as", "from_as", "fromasn"))
            source_type = relation(lookup(record, ("source_type", "source_relationship", "learned_from_type", "import_relationship", "from_type")))
            destination_type = relation(lookup(record, ("destination_type", "destination_relationship", "export_relationship", "to_type")))
            if source is None or destination is None or leaker is None:
                continue
            if source_type not in {"provider", "peer"} or destination_type == "unknown":
                continue
            item = {"leaker_as": leaker, "source_as": source, "destination_as": destination,
                    "source_type": source_type, "destination_type": destination_type}
            signature = tuple(item.values())
            if signature not in seen:
                found.append(item)
                seen.add(signature)
    return sorted(found, key=lambda item: tuple(item.values()))


def leaks(events):
    return [event for event in events if event["source_type"] in {"provider", "peer"}
            and event["destination_type"] != "customer"]


def solution_items(data):
    if isinstance(data, dict):
        data = lookup(data, ("possible_solutions", "solutions", "items", "options")) or data
    if isinstance(data, list):
        result = []
        for item in data:
            if isinstance(item, str):
                result.append((item, {"description": item}))
            elif isinstance(item, dict):
                label = lookup(item, ("name", "solution", "title", "description", "id"))
                result.append((str(label) if label is not None else json.dumps(item, sort_keys=True), item))
        return result
    if isinstance(data, dict):
        return [(str(key), value if isinstance(value, dict) else {"description": value}) for key, value in data.items()]
    return []


def boolean(record, names):
    value = lookup(record, names)
    return value if isinstance(value, bool) else None


def solution_effect(solution, edges, base_events):
    """Apply conservatively stated policy effects to copies of findings.

    Prose alone is accepted only for an explicit preference/adjacency removal or
    an explicit route export/import filter.  Timers and forwarding overrides do
    not alter either BGP policy graph.
    """
    text = json.dumps(solution, ensure_ascii=False).lower()
    new_edges = set(edges)
    new_events = list(base_events)
    explicit_cycle = boolean(solution, ("oscillation_resolved", "breaks_cycle", "cycle_removed"))
    explicit_leak = boolean(solution, ("route_leak_resolved", "stops_leak", "leak_removed"))

    # Machine-readable removed edges retain exact graph semantics.
    for key, value in solution.items() if isinstance(solution, dict) else ():
        if any(token in nk(key) for token in ("remove", "delete", "disable", "block")):
            for record in walk(value):
                left = first_asn(record, ("from_as", "fromasn", "source_as", "sourceasn", "from"))
                right = first_asn(record, ("to_as", "toasn", "destination_as", "destinationasn", "to"))
                if left is not None and right is not None:
                    new_edges.discard((left, right))

    disables_peer = bool(re.search(r"\b(disable|remove|eliminate)\b.{0,50}\b(peer|peering|adjacen)", text))
    routing_intent = bool(re.search(r"\b(enforce|force)\b.{0,80}\bhub.?to.?hub\b.{0,80}\b(only|through)\b", text))
    stop_preference = bool(re.search(r"\b(stop|remove|disable|eliminate)\b.{0,70}\bprefer(?:ring|ence)?\b", text))
    hierarchy = "preference hierarchy" in text and "peer" in text and ">" in text
    if disables_peer or routing_intent or hierarchy:
        # The stated intervention removes use of the peer adjacency; delete
        # preference dependencies that form mutual peer choices.
        for left, right in list(new_edges):
            if (right, left) in new_edges:
                new_edges.discard((left, right))
    if stop_preference:
        mentioned = [int(x) for x in re.findall(r"\b(?:asn\s*)?(\d{2,})\b", text)]
        removed = False
        for left, right in list(new_edges):
            if left in mentioned and right in mentioned:
                new_edges.discard((left, right)); removed = True
        if not removed and len(new_edges) == 1:
            new_edges.clear()

    # A filter is a leak remedy only when it explicitly controls export of the
    # provider/peer route, or explicitly rejects the offending import.  A
    # generic route map, a filter of routes learned from a different peer, and
    # a statement to stop *preferring* a route do not change this export.
    no_export = bool(re.search(r"\b(no-export|no export)\b", text))
    explicit_export_block = bool(re.search(
        r"\b(block|deny|withdraw)\b.{0,100}\b(advertis|announc|export)", text))
    provider_peer_filter = ("provider" in text and "peer" in text and
                            bool(re.search(r"\b(block|deny|filter)\b", text)))
    explicit_import_reject = ("reject" in text and "peer" in text and
                               bool(re.search(r"\b(route|routes|as.?path)\b", text)))
    export_filter = no_export or explicit_export_block or provider_peer_filter or explicit_import_reject
    # Removing the peer adjacency also removes advertisements to that peer.
    if export_filter or disables_peer or routing_intent:
        new_events = []
    if explicit_cycle is True:
        new_edges = set()
    if explicit_cycle is False:
        new_edges = set(edges)
    if explicit_leak is True:
        new_events = []
    if explicit_leak is False:
        new_events = list(base_events)
    return new_edges, new_events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="/app/data")
    parser.add_argument("--output", default="/app/output/oscillation_report.json")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        try:
            config = json.load(sys.stdin)
            if isinstance(config, dict):
                args.data_dir = config.get("data_dir", args.data_dir)
                args.output = config.get("output", args.output)
        except json.JSONDecodeError:
            pass
    directory = Path(args.data_dir)
    preferences = read_json(required(directory, "preferences.json"))
    read_json(required(directory, "route.json"))
    read_json(required(directory, "local_pref.json"))
    solutions = read_json(required(directory, "possible_solutions.json"))
    # Route events may be separated from the origin route.  Inspect JSON
    # sidecars rather than assuming a single route.json representation.
    data_sets = [read_json(path) for path in directory.rglob("*.json")
                 if path.name not in {"possible_solutions.json", "preferences.json", "local_pref.json"}]
    edges = preference_edges(preferences)
    base_events = advertisements(data_sets)
    base_cycle, base_leaks = cycle(edges), leaks(base_events)
    results = {}
    for label, solution in solution_items(solutions):
        changed_edges, changed_events = solution_effect(solution, edges, base_events)
        results[label] = {
            "oscillation_resolved": bool(base_cycle) and not bool(cycle(changed_edges)),
            "route_leak_resolved": bool(base_leaks) and not bool(leaks(changed_events)),
        }
    report = {
        "oscillation_detected": bool(base_cycle),
        "oscillation_cycle": base_cycle,
        "affected_ases": sorted(set(base_cycle)),
        "route_leak_detected": bool(base_leaks),
        "route_leaks": base_leaks,
        "solution_results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("analyze_bgp: " + str(exc), file=sys.stderr)
        sys.exit(2)
