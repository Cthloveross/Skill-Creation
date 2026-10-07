#!/usr/bin/env python3
"""Schema-tolerant BGP policy analyzer. JSON stdin -> JSON stdout."""
import copy
import json
import os
import re
import sys
from pathlib import Path

REL = {"customer", "peer", "provider"}
SOURCE_KEYS = ("source_as", "origin_as", "route_source_as", "learned_from_as", "from_as", "source", "origin")
DEST_KEYS = ("destination_as", "advertised_to_as", "export_to_as", "to_as", "destination", "advertised_to", "export_to", "to")
LEAKER_KEYS = ("leaker_as", "advertiser_as", "advertising_as", "hub_as", "exporter_as")
PREF_FROM = ("from_as", "source_as", "from", "source", "hub", "hub_as", "asn", "as_number")
PREF_TO = ("preferred_as", "preferred_hub", "next_hop_as", "next_hop", "to_as", "destination_as", "to", "destination")


def die(message):
    print(json.dumps({"error": message}), file=sys.stderr)
    raise SystemExit(2)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die("cannot read JSON %s: %s" % (path, e))


def find_file(directory, wanted):
    try:
        names = {p.name.lower(): p for p in Path(directory).iterdir() if p.is_file()}
    except OSError:
        return None
    return names.get(wanted.lower())


def resolve_data_dir(requested):
    required = ("route.json", "preferences.json", "local_pref.json", "possible_solutions.json")
    candidates = [Path(requested)]
    fallback = Path("/app/environment/data")
    if fallback != Path(requested):
        candidates.append(fallback)
    for candidate in candidates:
        if all(find_file(candidate, name) for name in required):
            return candidate
    die("required route.json, preferences.json, local_pref.json, and possible_solutions.json were not found")


def asn(value):
    """Return a valid ASN as int, accepting normal export representations."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(?:as)?\s*(\d+)\s*", value, re.I)
        if m:
            return int(m.group(1))
    return None


def norm_rel(value):
    if not isinstance(value, str):
        return None
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"customer": "customer", "customer_to_provider": "customer",
               "peer": "peer", "peering": "peer", "provider": "provider",
               "provider_to_customer": "provider"}
    return aliases.get(v)


def records(value):
    """Yield every object in an arbitrarily nested JSON export."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from records(child)
    elif isinstance(value, list):
        for child in value:
            yield from records(child)


def first_value(row, keys):
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def relation_from(row, kind):
    direct = (("source_type", "learned_from_type", "ingress_type", "from_type") if kind == "source"
              else ("destination_type", "export_type", "egress_type", "to_type"))
    value = first_value(row, direct)
    if norm_rel(value):
        return norm_rel(value)
    # Common forms: relationships: {source: "provider", destination: "peer"}
    for container_key in ("relationships", "relationship", "route_relationships", "policy"):
        child = row.get(container_key)
        if isinstance(child, dict):
            value = first_value(child, (kind, kind + "_type", "from" if kind == "source" else "to"))
            if norm_rel(value):
                return norm_rel(value)
    return None


def extract_preferences(data):
    edges = set()
    for row in records(data):
        a, b = asn(first_value(row, PREF_FROM)), asn(first_value(row, PREF_TO))
        if a is not None and b is not None and a != b:
            edges.add((a, b))
        # Supports compact maps such as {"65002": 65003}.
        for key, value in row.items():
            a, b = asn(key), asn(value)
            if a is not None and b is not None and a != b:
                edges.add((a, b))
    return edges


def path_asns(row):
    for key in ("as_path", "aspath", "path", "as_sequence"):
        value = row.get(key)
        if isinstance(value, list):
            found = [asn(x) for x in value]
            found = [x for x in found if x is not None]
            if len(found) >= 2:
                return found
    return []


def extract_ads(data):
    found = []
    seen = set()
    for row in records(data):
        src_type, dst_type = relation_from(row, "source"), relation_from(row, "destination")
        # Relationship evidence is mandatory: do not manufacture leak evidence.
        if src_type not in REL or dst_type not in REL:
            continue
        path = path_asns(row)
        source = asn(first_value(row, SOURCE_KEYS))
        destination = asn(first_value(row, DEST_KEYS))
        leaker = asn(first_value(row, LEAKER_KEYS))
        if source is None and path:
            source = path[0]
        if leaker is None and len(path) >= 2:
            leaker = path[-2]
        # A three-AS advertised path can encode the destination as its final AS.
        if destination is None and len(path) >= 3:
            destination = path[-1]
        if None in (source, destination, leaker):
            continue
        item = {"leaker_as": leaker, "source_as": source, "destination_as": destination,
                "source_type": src_type, "destination_type": dst_type}
        key = tuple(item[k] for k in ("leaker_as", "source_as", "destination_as", "source_type", "destination_type"))
        if key not in seen:
            seen.add(key)
            found.append(item)
    return found


def cycle_in(edges):
    graph = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set())
    state, stack = {}, []
    def visit(node):
        state[node] = 1
        stack.append(node)
        for nxt in sorted(graph[node]):
            if state.get(nxt, 0) == 1:
                return stack[stack.index(nxt):]
            if state.get(nxt, 0) == 0:
                answer = visit(nxt)
                if answer:
                    return answer
        stack.pop()
        state[node] = 2
        return None
    for node in sorted(graph):
        if state.get(node, 0) == 0:
            answer = visit(node)
            if answer:
                return answer
    return []


def invalid_ads(advertisements):
    return [a for a in advertisements if a["source_type"] in ("peer", "provider") and a["destination_type"] != "customer"]


def solution_items(data):
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        for key in ("solutions", "possible_solutions", "items", "options"):
            if isinstance(data.get(key), list):
                raw = data[key]
                break
        else:
            # Mapping from visible solution title to its stated effect.
            raw = [{"name": k, "effect": v} for k, v in data.items()]
    else:
        raw = []
    result = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            result.append((item, {"description": item}))
        elif isinstance(item, dict):
            name = first_value(item, ("name", "title", "solution", "description", "id"))
            result.append((str(name if name is not None else "solution_%d" % (index + 1)), item))
    return result


def bool_effect(obj, names):
    for row in records(obj):
        for name in names:
            value = row.get(name)
            if value is True:
                return True
    return False


def pair_list(value):
    pairs = set()
    if isinstance(value, list):
        for x in value:
            if isinstance(x, (list, tuple)) and len(x) >= 2:
                a, b = asn(x[0]), asn(x[1])
            elif isinstance(x, dict):
                a, b = asn(first_value(x, PREF_FROM)), asn(first_value(x, PREF_TO))
            else:
                continue
            if a is not None and b is not None:
                pairs.add((a, b))
    return pairs


def text_of(value):
    chunks = []
    for row in records(value):
        for key in ("description", "effect", "action", "details", "name", "title", "solution"):
            if isinstance(row.get(key), str):
                chunks.append(row[key])
    return " ".join(chunks).lower()


def simulate(solution, base_edges, base_ads):
    edges, ads = set(base_edges), copy.deepcopy(base_ads)
    # Explicit machine-readable policy effects take precedence over loose wording.
    for row in records(solution):
        for key in ("remove_preference_edges", "removed_preference_edges", "disable_preferences"):
            edges -= pair_list(row.get(key))
        for key in ("add_preference_edges", "added_preference_edges"):
            edges |= pair_list(row.get(key))
        replacement = row.get("preferences_after")
        if replacement is not None:
            replacement_edges = extract_preferences(replacement)
            if replacement_edges:
                edges = replacement_edges
        for key in ("remove_advertisements", "blocked_advertisements", "stop_advertisements"):
            if row.get(key) is True:
                ads = []
    text = text_of(solution)
    explicit_break = bool_effect(solution, ("breaks_preference_cycle", "oscillation_fixed", "oscillation_resolved"))
    explicit_stop = bool_effect(solution, ("stops_route_advertising", "blocks_route_leaks", "route_leak_fixed", "route_leak_resolved"))
    # These patterns express a policy effect, unlike timer/monitoring/forwarding changes.
    text_break = bool(re.search(r"\b(break|eliminate|remove)\b.{0,80}\b(preference )?cycle\b", text))
    text_stop = bool(re.search(r"\b(stop|block|filter|deny|disable)\b.{0,100}\b(advertis|propagat|export)", text))
    if explicit_break or text_break:
        # The stated effect is a complete cycle break; remove current cycle edges.
        cyc = cycle_in(edges)
        if cyc:
            edges.discard((cyc[0], cyc[1] if len(cyc) > 1 else cyc[0]))
    if explicit_stop or text_stop:
        ads = []
    return edges, ads


def main():
    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        die("stdin must be one JSON object: %s" % e)
    if not isinstance(config, dict):
        die("stdin JSON must be an object")
    directory = resolve_data_dir(config.get("data_dir", "/app/data"))
    route = load_json(find_file(directory, "route.json"))
    preferences = load_json(find_file(directory, "preferences.json"))
    load_json(find_file(directory, "local_pref.json"))  # required relationship vocabulary/weights input
    solutions = load_json(find_file(directory, "possible_solutions.json"))
    edges, ads = extract_preferences(preferences), extract_ads(route)
    cycle, leaks = cycle_in(edges), invalid_ads(ads)
    report = {"oscillation_detected": bool(cycle), "oscillation_cycle": cycle,
              "affected_ases": sorted(cycle), "route_leak_detected": bool(leaks),
              "route_leaks": leaks, "solution_results": {}}
    if cycle or leaks:
        for name, solution in solution_items(solutions):
            new_edges, new_ads = simulate(solution, edges, ads)
            report["solution_results"][name] = {
                "oscillation_resolved": not bool(cycle_in(new_edges)),
                "route_leak_resolved": not bool(invalid_ads(new_ads))}
    output = Path(config.get("output_path", "/app/output/oscillation_report.json"))
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=False)
            f.write("\n")
    except OSError as e:
        die("cannot write report %s: %s" % (output, e))
    print(json.dumps({"output_path": str(output), "preference_edges": len(edges),
                      "advertisements": len(ads), "route_leaks": len(leaks)}))

if __name__ == "__main__":
    main()
