#!/usr/bin/env python3
"""Validate a dialogue graph. Reads one JSON request from stdin and emits JSON."""
from __future__ import annotations

import json
import sys
from typing import Any


def validate(graph: Any, terminal_ids: list[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["graph must be an object"]
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes must be a nonempty array")
        return errors
    if not isinstance(edges, list):
        errors.append("edges must be an array")
        return errors

    ids: list[str] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append("node %d is not an object" % index)
            continue
        for key in ("id", "text", "speaker", "type"):
            if key not in node or not isinstance(node[key], str):
                errors.append("node %d has no string %s" % (index, key))
        if isinstance(node.get("id"), str) and node["id"]:
            ids.append(node["id"])
        else:
            errors.append("node %d has an empty id" % index)
        if node.get("type") not in ("line", "choice"):
            errors.append("node %d type must be line or choice" % index)
    if len(ids) != len(set(ids)):
        errors.append("node IDs are duplicated")

    declared = set(ids)
    external = {item.casefold() for item in terminal_ids}
    adjacency = {item: [] for item in declared}
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append("edge %d is not an object" % index)
            continue
        for key in ("from", "to", "text"):
            if key not in edge or not isinstance(edge[key], str):
                errors.append("edge %d has no string %s" % (index, key))
        source, target = edge.get("from"), edge.get("to")
        if source not in declared:
            errors.append("edge %d source is not declared" % index)
            continue
        if target in declared:
            adjacency[source].append(target)
        elif not isinstance(target, str) or target.casefold() not in external:
            errors.append("edge %d target is unresolved: %r" % (index, target))

    if ids:
        seen: set[str] = set()
        stack = [ids[0]]
        while stack:
            node_id = stack.pop()
            if node_id not in seen:
                seen.add(node_id)
                stack.extend(adjacency[node_id])
        missing = [node_id for node_id in ids if node_id not in seen]
        if missing:
            errors.append("unreachable nodes: " + ", ".join(missing))
    return errors


def main() -> int:
    try:
        request = json.load(sys.stdin)
        terminals = request.get("terminal_ids", ["End"])
        if not isinstance(terminals, list) or not all(isinstance(item, str) for item in terminals):
            raise ValueError("terminal_ids must be an array of strings")
        errors = validate(request.get("graph"), terminals)
        json.dump({"valid": not errors, "errors": errors}, sys.stdout)
        sys.stdout.write("\n")
        return 0 if not errors else 1
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"valid": False, "errors": [str(exc)]}, sys.stdout)
        sys.stdout.write("\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
