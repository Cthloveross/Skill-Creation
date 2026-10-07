#!/usr/bin/env python3
"""Dialogue script -> graph parser (task deliverable).

Exposes `parse_script(text)` returning {"nodes": [...], "edges": [...]}.
Run directly to read a script file and write JSON + DOT outputs:
    python solution.py [script_path] [out_json] [out_dot]
Defaults: /app/script.txt, /app/dialogue.json, /app/dialogue.dot
"""
import json
import re
import sys

# A header line is a bracketed id that fills the whole line, e.g. "[GateScene]".
HEADER_RE = re.compile(r'^\s*\[([^\]]+)\]\s*$')
# A numbered choice option, e.g. "1. text" or "2) text".
CHOICE_RE = re.compile(r'^\s*(\d+)\s*[.)]\s*(.*)$')
# Trailing transition arrow "-> Target".
ARROW_RE = re.compile(r'->\s*(\S+)\s*$')

# Terminal sentinels that may be edge targets without a declared node.
TERMINALS = {"End"}


def _split_target(s):
    """Return (text_without_arrow, target_or_None), preserving source text."""
    m = ARROW_RE.search(s)
    if m:
        return s[:m.start()].rstrip(), m.group(1)
    return s.strip(), None


def _split_speaker(s):
    """Return (speaker, text). Speaker is text before the first ':' if sane."""
    idx = s.find(':')
    if idx != -1:
        cand = s[:idx].strip()
        if cand and '->' not in cand and '[' not in cand:
            return cand, s[idx + 1:].strip()
    return "", s.strip()


def parse_script(text):
    """Parse dialogue script text into {"nodes": [...], "edges": [...]}."""
    records = []
    current = None
    for raw in text.splitlines():
        line = raw.rstrip('\r\n')
        if not line.strip():
            continue
        hm = HEADER_RE.match(line)
        if hm:
            current = {"id": hm.group(1).strip(), "body": []}
            records.append(current)
        elif current is not None:
            current["body"].append(line.strip())
        # lines before the first header are ignored

    nodes = {}
    order = []
    edges = []

    for rec in records:
        nid = rec["id"]
        choice_items = []  # (option_text, target)
        speaker = ""
        texts = []
        line_target = None
        for b in rec["body"]:
            cm = CHOICE_RE.match(b)
            if cm:
                opt_text, target = _split_target(cm.group(2))
                choice_items.append((opt_text, target))
            else:
                btext, target = _split_target(b)
                sp, tx = _split_speaker(btext)
                if sp and not speaker:
                    speaker = sp
                if tx:
                    texts.append(tx)
                if target:
                    line_target = target

        ntype = "choice" if choice_items else "line"
        node = {
            "id": nid,
            "text": " ".join(texts).strip(),
            "speaker": speaker,
            "type": ntype,
        }
        if nid not in nodes:
            order.append(nid)
        nodes[nid] = node  # redeclaration overwrites fields, no duplicate node

        if choice_items:
            for opt_text, target in choice_items:
                if target:
                    edges.append({"from": nid, "to": target, "text": opt_text})
            if line_target:
                edges.append({"from": nid, "to": line_target, "text": ""})
        elif line_target:
            edges.append({"from": nid, "to": line_target, "text": ""})

    return {"nodes": [nodes[i] for i in order], "edges": edges}


def validate(graph):
    """Return a list of constraint-violation messages (empty == valid)."""
    errors = []
    ids = [n["id"] for n in graph["nodes"]]
    idset = set(ids)
    if len(ids) != len(idset):
        errors.append("duplicate node ids present")
    for e in graph["edges"]:
        if e["to"] not in idset and e["to"] not in TERMINALS:
            errors.append("edge target not declared: %s" % e["to"])
    if ids:
        start = ids[0]
        adj = {}
        for e in graph["edges"]:
            adj.setdefault(e["from"], []).append(e["to"])
        seen = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, []):
                if nxt in idset and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        unreached = idset - seen
        if unreached:
            errors.append("unreachable nodes: " + ",".join(sorted(unreached)))
    return errors


def _escape(s):
    return (s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n'))


def to_dot(graph):
    out = ["digraph dialogue {"]
    for n in graph["nodes"]:
        prefix = (n["speaker"] + ": ") if n["speaker"] else ""
        label = "%s\n%s%s" % (n["id"], prefix, n["text"])
        shape = "box" if n["type"] == "line" else "diamond"
        out.append('  "%s" [label="%s" shape=%s];'
                   % (_escape(n["id"]), _escape(label), shape))
    for e in graph["edges"]:
        out.append('  "%s" -> "%s" [label="%s"];'
                   % (_escape(e["from"]), _escape(e["to"]), _escape(e["text"])))
    out.append("}")
    return "\n".join(out) + "\n"


def build_outputs(script_path, out_json, out_dot):
    with open(script_path, "r", encoding="utf-8") as f:
        text = f.read()
    graph = parse_script(text)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    with open(out_dot, "w", encoding="utf-8") as f:
        f.write(to_dot(graph))
    return graph


def main(argv):
    script_path = argv[1] if len(argv) > 1 else "/app/script.txt"
    out_json = argv[2] if len(argv) > 2 else "/app/dialogue.json"
    out_dot = argv[3] if len(argv) > 3 else "/app/dialogue.dot"
    graph = build_outputs(script_path, out_json, out_dot)
    errors = validate(graph)
    summary = {
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "first_node": graph["nodes"][0]["id"] if graph["nodes"] else None,
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
