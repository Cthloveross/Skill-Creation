#!/usr/bin/env python3
"""Discover BGP JSON inputs, calculate policy findings, and write/report JSON.

CLI input: --data-dir DIR --output FILE, with an optional JSON object on stdin
containing {"data_dir": str, "output": str}.  stdout is the report object.
"""
import argparse, copy, json, os, re, sys
from pathlib import Path

SOURCE_KEYS = ("source_as", "sourceasn", "source_asn", "learned_from_as", "upstream_as", "origin_as", "from_as", "fromasn")
DEST_KEYS = ("destination_as", "destinationasn", "destination_asn", "advertised_to_as", "export_to_as", "downstream_as", "to_as", "toasn")
LEAKER_KEYS = ("leaker_as", "advertiser_as", "hub_as", "exporter_as", "current_as", "from_as", "fromasn")
FROM_KEYS = ("from_as", "fromasn", "source_as", "sourceasn", "source_asn", "src_as", "src")
TO_KEYS = ("to_as", "toasn", "destination_as", "destinationasn", "destination_asn", "dst_as", "dst")
REL_SOURCE_KEYS = ("source_type", "source_relationship", "learned_from_type", "import_relationship", "from_type", "upstream_type")
REL_DEST_KEYS = ("destination_type", "destination_relationship", "export_relationship", "to_type", "downstream_type")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def number(v):
    if isinstance(v, bool): return None
    if isinstance(v, int): return v
    if isinstance(v, float) and v.is_integer(): return int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*\d+\s*", v): return int(v.strip())
    return None

def lookup(d, aliases):
    if not isinstance(d, dict): return None
    table = {norm(k): v for k, v in d.items()}
    for key in aliases:
        if norm(key) in table:
            return table[norm(key)]
    return None

def asn(d, aliases):
    v = lookup(d, aliases)
    if isinstance(v, dict):
        v = lookup(v, ("asn", "as", "id", "number"))
    return number(v)

def relationship(v):
    if isinstance(v, dict): v = lookup(v, ("type", "relationship", "role", "name"))
    s = norm(v or "")
    if "customer" in s or s in ("cust", "c"): return "customer"
    if "provider" in s or "transit" in s or s in ("prov", "p"): return "provider"
    if "peer" in s or s in ("peering", "peerpeer"): return "peer"
    return str(v).lower() if v is not None else "unknown"

def records(x):
    """Yield all dictionary records, retaining schema-independent discovery."""
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from records(v)
    elif isinstance(x, list):
        for v in x: yield from records(v)

def read_json(path):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError("invalid JSON in %s: %s" % (path, e))

def find_file(directory, basename):
    exact = Path(directory) / basename
    if exact.is_file(): return exact
    matches = [p for p in Path(directory).rglob("*.json") if p.name.lower() == basename.lower()]
    if not matches: raise FileNotFoundError("missing required input " + str(exact))
    return matches[0]

def preference_edges(data):
    out = set()
    for r in records(data):
        a, b = asn(r, FROM_KEYS), asn(r, TO_KEYS)
        # A route record is not a preference record unless preference wording exists.
        keys = " ".join(norm(k) for k in r)
        is_pref = any(x in keys for x in ("preference", "preferred", "localpref", "weight", "rank"))
        if a is not None and b is not None and (is_pref or ("from" in keys and "to" in keys)):
            out.add((a, b))
    return out

def explicit_edge_lists(obj, key_tokens):
    ans = set()
    if not isinstance(obj, dict): return ans
    for k, v in obj.items():
        if any(t in norm(k) for t in key_tokens):
            for r in records(v):
                a, b = asn(r, FROM_KEYS), asn(r, TO_KEYS)
                if a is not None and b is not None: ans.add((a,b))
    return ans

def find_cycle(edges):
    graph = {}
    for a,b in edges: graph.setdefault(a, set()).add(b)
    state, stack = {}, []
    def visit(a):
        state[a] = 1; stack.append(a)
        for b in sorted(graph.get(a, ())):
            if state.get(b, 0) == 1:
                return stack[stack.index(b):]
            if state.get(b, 0) == 0:
                got = visit(b)
                if got: return got
        stack.pop(); state[a] = 2
        return None
    for a in sorted(graph):
        if state.get(a,0) == 0:
            got = visit(a)
            if got:
                # rotate only; do not append starting ASN again
                m = min(range(len(got)), key=lambda i: got[i])
                return got[m:] + got[:m]
    return []

def route_leaks(data):
    ans, seen = [], set()
    for r in records(data):
        source, dest = asn(r, SOURCE_KEYS), asn(r, DEST_KEYS)
        leaker = asn(r, LEAKER_KEYS)
        sr = relationship(lookup(r, REL_SOURCE_KEYS))
        dr = relationship(lookup(r, REL_DEST_KEYS))
        # Support nested relationship objects commonly used in route exports.
        if sr == "unknown": sr = relationship(lookup(r, ("source", "learned_from", "upstream")))
        if dr == "unknown": dr = relationship(lookup(r, ("destination", "export_to", "downstream")))
        if source is None or dest is None or sr not in ("provider", "peer") or dr == "customer":
            continue
        if leaker is None:
            # A path's intermediate AS is the advertiser when available.
            path = lookup(r, ("as_path", "aspath", "path"))
            if isinstance(path, list) and len(path) >= 2: leaker = number(path[-2])
        if leaker is None: continue
        item = {"leaker_as": leaker, "source_as": source, "destination_as": dest,
                "source_type": sr, "destination_type": dr}
        sig = tuple(item.values())
        if sig not in seen: seen.add(sig); ans.append(item)
    return sorted(ans, key=lambda x: (x["leaker_as"],x["source_as"],x["destination_as"],x["source_type"],x["destination_type"]))

def solution_items(data):
    if isinstance(data, dict):
        container = lookup(data, ("possible_solutions", "solutions", "items", "options"))
        if container is None: container = data
    else: container = data
    if isinstance(container, dict):
        return [(str(k), v if isinstance(v,dict) else {"description":v}) for k,v in container.items()]
    if isinstance(container, list):
        out=[]
        for v in container:
            if isinstance(v, str): out.append((v,{"description":v}))
            elif isinstance(v, dict):
                label=lookup(v,("name","solution","description","title","id"))
                out.append((str(label) if label is not None else json.dumps(v,sort_keys=True),v))
        return out
    return []

def bool_field(d, aliases):
    v=lookup(d, aliases)
    return v if isinstance(v,bool) else None

def solution_result(sol, base_edges, base_leaks):
    text = json.dumps(sol, ensure_ascii=False).lower()
    explicit_o = bool_field(sol,("oscillation_resolved","resolves_oscillation","breaks_cycle","cycle_removed"))
    explicit_l = bool_field(sol,("route_leak_resolved","resolves_route_leak","stops_leak","leak_removed"))
    edges=set(base_edges)
    edges -= explicit_edge_lists(sol,("remove","delete","disable","block"))
    edges |= explicit_edge_lists(sol,("add","create"))
    # Structured policy changes can state which export relationship becomes customer/blocked.
    blocked = bool(re.search(r"\b(block|deny|filter|stop|disable|withdraw)\b.*\b(advert|export|propagat|route)\b", text))
    cycle_break = bool(re.search(r"\b(break|remove|disable|eliminate)\b.*\b(cycle|preference|adjacen|peer)\b", text))
    cycle_break = cycle_break or bool(re.search(r"\b(change|set|lower)\b.*\b(local.?pref|routing preference|preference)\b", text))
    # An intervention only resolves a currently-present issue if its relevant graph is absent after effect.
    remaining_cycle = find_cycle(edges)
    ores = (not remaining_cycle) if (explicit_o is True or cycle_break or edges != set(base_edges)) else False
    if explicit_o is False: ores = False
    # Without a complete structured advertisement transform, only explicit export blocking is evidence.
    lres = bool(blocked) if base_leaks else False
    if explicit_l is not None: lres = explicit_l and bool(base_leaks)
    return {"oscillation_resolved": bool(ores), "route_leak_resolved": bool(lres)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data-dir",default="/app/data"); ap.add_argument("--output",default="/app/output/oscillation_report.json")
    args=ap.parse_args()
    if not sys.stdin.isatty():
        try:
            cfg=json.load(sys.stdin)
            if isinstance(cfg,dict):
                args.data_dir=cfg.get("data_dir",args.data_dir); args.output=cfg.get("output",args.output)
        except json.JSONDecodeError: pass
    pref=read_json(find_file(args.data_dir,"preferences.json"))
    routes=read_json(find_file(args.data_dir,"route.json"))
    # local_pref is deliberately loaded: relationship definitions may be inspected by executor;
    # route records retain the concrete relation used for valley-free evaluation.
    read_json(find_file(args.data_dir,"local_pref.json"))
    sols=read_json(find_file(args.data_dir,"possible_solutions.json"))
    edges=preference_edges(pref); cycle=find_cycle(edges); leaks=route_leaks(routes)
    results={label: solution_result(sol,edges,leaks) for label,sol in solution_items(sols)}
    report={"oscillation_detected":bool(cycle),"oscillation_cycle":cycle,"affected_ases":sorted(set(cycle)),
            "route_leak_detected":bool(leaks),"route_leaks":leaks,"solution_results":results}
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report))
if __name__ == "__main__":
    try: main()
    except Exception as e:
        print("analyze_bgp: " + str(e),file=sys.stderr); sys.exit(2)
