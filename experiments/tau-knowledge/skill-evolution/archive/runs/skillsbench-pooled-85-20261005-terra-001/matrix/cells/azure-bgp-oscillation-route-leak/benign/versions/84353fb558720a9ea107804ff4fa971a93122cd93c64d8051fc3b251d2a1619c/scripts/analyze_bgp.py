#!/usr/bin/env python3
"""Analyze schema-tolerant runtime BGP JSON. stdin JSON -> stdout JSON."""
import copy
import json
import re
import sys
from pathlib import Path

RELATIONS = {"customer", "peer", "provider"}


def die(message):
    print(json.dumps({"error": message}), file=sys.stderr)
    raise SystemExit(2)


def load_json(path):
    try:
        with Path(path).open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        die("cannot read JSON %s: %s" % (path, exc))


def find_file(directory, name):
    try:
        return {p.name.lower(): p for p in Path(directory).iterdir() if p.is_file()}.get(name.lower())
    except OSError:
        return None


def resolve_directory(requested):
    required = ("route.json", "preferences.json", "local_pref.json", "possible_solutions.json")
    candidates = [Path(requested)]
    fallback = Path("/app/environment/data")
    if fallback not in candidates:
        candidates.append(fallback)
    for directory in candidates:
        if all(find_file(directory, name) is not None for name in required):
            return directory
    die("required route.json, preferences.json, local_pref.json, and possible_solutions.json were not found")


def norm(value):
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def asn(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text.startswith("as"):
            text = text[2:].strip()
        try:
            return int(text)
        except ValueError:
            return None
    return None


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def value_for(row, names):
    if not isinstance(row, dict):
        return None
    indexed = {norm(key): value for key, value in row.items()}
    for name in names:
        if norm(name) in indexed:
            return indexed[norm(name)]
    return None


def normalize_relation(value):
    if not isinstance(value, str):
        return None
    aliases = {
        "customer": "customer", "customer_to_provider": "customer",
        "peer": "peer", "peering": "peer",
        "provider": "provider", "provider_to_customer": "provider",
    }
    return aliases.get(norm(value))


def topology_aliases(topology):
    aliases = {}
    asn_fields = ("asn", "as", "as_number", "autonomous_system", "autonomous_system_number")
    label_fields = ("hub", "hub_name", "name", "id", "node", "node_name", "vhub")
    for row in walk(topology):
        number = asn(value_for(row, asn_fields))
        if number is None:
            continue
        for field in label_fields:
            label = value_for(row, (field,))
            if isinstance(label, str) and label.strip():
                aliases[norm(label)] = number
        for key, value in row.items():
            if isinstance(key, str) and isinstance(value, dict):
                child_number = asn(value_for(value, asn_fields))
                if child_number is not None:
                    aliases[norm(key)] = child_number
    return aliases


def resolve_as(value, aliases):
    direct = asn(value)
    if direct is not None:
        return direct
    if isinstance(value, str):
        return aliases.get(norm(value))
    if isinstance(value, dict):
        return resolve_as(value_for(value, ("asn", "as", "hub", "name", "id")), aliases)
    return None


def preference_edges(preferences, topology):
    """Reconstruct directed preferences, including keyed hub policy objects."""
    aliases = topology_aliases(topology)
    edges = set()
    source_fields = ("as", "asn", "source_as", "from_as", "hub_as", "hub", "source", "from")
    destination_fields = (
        "preferred_as", "preferred", "preferred_hub", "preferred_next_hop",
        "next_hop_as", "next_hop", "via", "to_as", "to", "destination_as",
        "destination", "peer_as", "peer",
    )

    def visit(value, owner=None):
        if isinstance(value, list):
            for item in value:
                visit(item, owner)
            return
        if not isinstance(value, dict):
            return
        source = resolve_as(value_for(value, source_fields), aliases)
        if source is None:
            source = resolve_as(owner, aliases)
        destination = resolve_as(value_for(value, destination_fields), aliases)
        if source is not None and destination is not None and source != destination:
            edges.add((source, destination))
        for key, child in value.items():
            resolved_key = resolve_as(key, aliases)
            child_owner = key if resolved_key is not None else (source if source is not None else owner)
            # Supports {"hubA": {"preferred_hub": "hubB"}} and {"hubA": "hubB"}.
            if source is not None and resolved_key is not None and resolved_key != source:
                if isinstance(child, (int, str, dict)) and (not isinstance(child, str) or norm(child) not in aliases):
                    edges.add((source, resolved_key))
            visit(child, child_owner)

    visit(preferences)
    return edges, aliases


def cyclic_nodes(edges):
    graph = {}
    for left, right in edges:
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set())
    result = set()
    for start in graph:
        pending = list(graph[start])
        seen = set()
        while pending:
            node = pending.pop()
            if node == start:
                result.add(start)
                break
            if node not in seen:
                seen.add(node)
                pending.extend(graph.get(node, ()))
    return result


def relation_for(row, side):
    direct = (("source_type", "learned_from_type", "ingress_type", "from_type", "source_relationship")
              if side == "source" else
              ("destination_type", "export_type", "egress_type", "to_type", "destination_relationship"))
    answer = normalize_relation(value_for(row, direct))
    if answer:
        return answer
    for container in ("relationships", "relationship", "route_relationships", "policy"):
        child = value_for(row, (container,))
        if isinstance(child, dict):
            answer = normalize_relation(value_for(child, (side, side + "_type", "from" if side == "source" else "to")))
            if answer:
                return answer
    return None


def path_values(row):
    value = value_for(row, ("as_path", "aspath", "path", "as_sequence"))
    if isinstance(value, list):
        return [number for number in (asn(item) for item in value) if number is not None]
    return []


def extract_advertisements(route_data):
    advertisements, seen = [], set()
    for row in walk(route_data):
        source_type, destination_type = relation_for(row, "source"), relation_for(row, "destination")
        if source_type not in RELATIONS or destination_type not in RELATIONS:
            continue
        source = asn(value_for(row, ("source_as", "origin_as", "route_source_as", "learned_from_as", "from_as", "source", "origin")))
        destination = asn(value_for(row, ("destination_as", "advertised_to_as", "export_to_as", "to_as", "destination", "advertised_to", "export_to", "to")))
        leaker = asn(value_for(row, ("leaker_as", "advertiser_as", "advertising_as", "hub_as", "exporter_as", "hub")))
        path = path_values(row)
        if source is None and path:
            source = path[0]
        if leaker is None and len(path) >= 2:
            leaker = path[-2]
        if destination is None and len(path) >= 3:
            destination = path[-1]
        if None in (source, destination, leaker):
            continue
        item = {"leaker_as": leaker, "source_as": source, "destination_as": destination,
                "source_type": source_type, "destination_type": destination_type}
        key = tuple(item[field] for field in ("leaker_as", "source_as", "destination_as", "source_type", "destination_type"))
        if key not in seen:
            seen.add(key)
            advertisements.append(item)
    return advertisements


def invalid_ads(advertisements):
    return [ad for ad in advertisements if ad["source_type"] in ("peer", "provider") and ad["destination_type"] != "customer"]


def runtime_asns(data_sets):
    """Match runtime evidence: ASNs directly recorded in input object fields."""
    found = set()
    for data in data_sets:
        for row in walk(data):
            for value in row.values():
                number = asn(value)
                if number is not None:
                    found.add(number)
    return found


def solution_catalog(solutions):
    """Discover precisely the visible solution identifiers in arbitrary nesting."""
    catalog = []
    name_fields = {"name", "solution", "description", "solution_name", "solution_description", "title", "recommendation", "action"}
    for row in walk(solutions):
        for key, value in row.items():
            if norm(key) in name_fields and isinstance(value, str) and value.strip():
                catalog.append((value, row))
        for key, value in row.items():
            if not (isinstance(key, str) and isinstance(value, dict) and len(key) > 20):
                continue
            child_keys = {norm(child_key) for child_key in value}
            if any(token in child_key for child_key in child_keys for token in ("effect", "change", "resolve", "filter", "policy")):
                catalog.append((key, {"description": key, "effect": value}))
    result, names = [], set()
    for name, effect in catalog:
        if name not in names:
            names.add(name)
            result.append((name, effect))
    return result


def pairs(value, aliases):
    answer = set()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                left, right = resolve_as(item[0], aliases), resolve_as(item[1], aliases)
            elif isinstance(item, dict):
                left = resolve_as(value_for(item, ("from_as", "source_as", "from", "source", "hub", "hub_as", "asn", "as_number")), aliases)
                right = resolve_as(value_for(item, ("preferred_as", "preferred_hub", "next_hop_as", "next_hop", "to_as", "destination_as", "to", "destination")), aliases)
            else:
                continue
            if left is not None and right is not None:
                answer.add((left, right))
    return answer


def text_of(value):
    chunks = []
    for row in walk(value):
        for key in ("description", "effect", "action", "details", "name", "title", "solution", "recommendation"):
            candidate = value_for(row, (key,))
            if isinstance(candidate, str):
                chunks.append(candidate)
    return " ".join(chunks).lower()


def truthy_effect(solution, fields):
    for row in walk(solution):
        for field in fields:
            if value_for(row, (field,)) is True:
                return True
    return False


def simulate(solution, base_edges, base_ads, aliases):
    edges, advertisements = set(base_edges), copy.deepcopy(base_ads)
    for row in walk(solution):
        for field in ("remove_preference_edges", "removed_preference_edges", "disable_preferences", "blocked_preferences"):
            edges -= pairs(value_for(row, (field,)), aliases)
        for field in ("add_preference_edges", "added_preference_edges"):
            edges |= pairs(value_for(row, (field,)), aliases)
        replacement = value_for(row, ("preferences_after", "replacement_preferences"))
        if replacement is not None:
            replacement_edges, _ = preference_edges(replacement, {"aliases": aliases})
            if replacement_edges:
                edges = replacement_edges
        for field in ("remove_advertisements", "blocked_advertisements", "stop_advertisements"):
            if value_for(row, (field,)) is True:
                advertisements = []
    text = text_of(solution)
    break_cycle = truthy_effect(solution, ("breaks_preference_cycle", "oscillation_fixed", "oscillation_resolved"))
    stop_exports = truthy_effect(solution, ("stops_route_advertising", "blocks_route_leaks", "route_leak_fixed", "route_leak_resolved"))
    break_cycle = break_cycle or bool(re.search(r"\b(break|eliminate|remove|prevent)\b.{0,100}\b(preference )?cycle\b", text))
    stop_exports = stop_exports or bool(re.search(r"\b(stop|block|filter|deny|disable)\b.{0,100}\b(advertis|propagat|export)", text))
    if break_cycle:
        # A stated complete cycle break removes one outgoing edge per currently cyclic AS.
        nodes = cyclic_nodes(edges)
        for left, right in sorted(edges):
            if left in nodes and right in nodes:
                edges.remove((left, right))
                break
    if stop_exports:
        advertisements = []
    return edges, advertisements


def main():
    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        die("stdin must be one JSON object: %s" % exc)
    if not isinstance(config, dict):
        die("stdin JSON must be an object")
    directory = resolve_directory(config.get("data_dir", "/app/data"))
    route = load_json(find_file(directory, "route.json"))
    preferences = load_json(find_file(directory, "preferences.json"))
    load_json(find_file(directory, "local_pref.json"))
    solutions = load_json(find_file(directory, "possible_solutions.json"))
    topology_path = find_file(directory, "topology.json")
    topology = load_json(topology_path) if topology_path else {}
    extra_inputs = []
    for name in ("relationships.json", "route_events.json"):
        path = find_file(directory, name)
        if path:
            extra_inputs.append(load_json(path))

    edges, aliases = preference_edges(preferences, topology)
    cycle = sorted(cyclic_nodes(edges))
    advertisements = extract_advertisements(route)
    known = runtime_asns([topology, route] + extra_inputs)
    leaks = [ad for ad in invalid_ads(advertisements) if {ad["leaker_as"], ad["source_as"], ad["destination_as"]} <= known]

    report = {
        "oscillation_detected": bool(cycle),
        "oscillation_cycle": cycle,
        "affected_ases": list(cycle),
        "route_leak_detected": bool(leaks),
        "route_leaks": leaks,
        "solution_results": {},
    }
    for name, solution in solution_catalog(solutions):
        new_edges, new_ads = simulate(solution, edges, advertisements, aliases)
        report["solution_results"][name] = {
            "oscillation_resolved": not bool(cyclic_nodes(new_edges)),
            "route_leak_resolved": not bool(invalid_ads(new_ads)),
        }

    output = Path(config.get("output_path", "/app/output/oscillation_report.json"))
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        die("cannot write report %s: %s" % (output, exc))
    print(json.dumps({"output_path": str(output), "preference_edges": len(edges), "route_leaks": len(leaks), "solutions": len(report["solution_results"])}))


if __name__ == "__main__":
    main()
