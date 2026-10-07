"""Dialogue-script parser used by the dialogue-parser artifact task."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# These expressions intentionally mirror the public bracket-record grammar.
HEADER_RE = re.compile(r"^\s*\[([^\]\r\n]+)\]\s*$")
CHOICE_RE = re.compile(r"^\s*\d+\.\s*")
SPEAKER_RE = re.compile(r"^\s*([^:]+):\s*(.*)$")


def _normal_target(value: str) -> str:
    """Return a transition target, unwrapping a complete bracketed target."""
    target = value.strip()
    match = HEADER_RE.match(target)
    return match.group(1).strip() if match else target


def _make_record(record_id: str, body: list[str]) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Build one node and all arrows authored within that record."""
    # The source text is retained verbatim apart from surrounding line whitespace,
    # matching the record grammar and making labels useful to dialogue readers.
    content = [line.strip() for line in body if line.strip()]
    is_choice = any(CHOICE_RE.match(line) for line in content)
    speaker = ""
    if not is_choice and content:
        match = SPEAKER_RE.match(content[0])
        if match:
            speaker = match.group(1).strip()

    edges: list[dict[str, str]] = []
    for line in content:
        if "->" not in line:
            continue
        # A final split supports authored dialogue that itself happens to contain ->.
        left, right = line.rsplit("->", 1)
        target = _normal_target(right)
        if not target:
            raise ValueError("transition has an empty target in record " + record_id)
        edges.append({"from": record_id, "to": target, "text": left.strip()})

    return (
        {
            "id": record_id,
            "text": "\n".join(content),
            "speaker": speaker,
            "type": "choice" if is_choice else "line",
        },
        edges,
    )


def parse_script(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse bracketed dialogue records into the required nodes/edges graph.

    Every declaration is retained once in source order.  A target such as End is
    intentionally only an edge target unless it is separately declared by a
    bracketed record in the input.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    records: list[tuple[str, list[str]]] = []
    record_id: str | None = None
    lines: list[str] = []
    seen: set[str] = set()

    def finish() -> None:
        nonlocal record_id, lines
        if record_id is not None:
            records.append((record_id, lines))
        record_id = None
        lines = []

    for raw in text.splitlines():
        header = HEADER_RE.match(raw)
        if header:
            finish()
            node_id = header.group(1).strip()
            if not node_id:
                raise ValueError("empty record identifier")
            if node_id in seen:
                raise ValueError("duplicate record identifier: " + node_id)
            seen.add(node_id)
            record_id = node_id
        elif record_id is not None:
            lines.append(raw)
        elif raw.strip():
            raise ValueError("content occurs before the first record header")
    finish()

    if not records:
        raise ValueError("script contains no bracketed records")

    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    for node_id, record_lines in records:
        node, record_edges = _make_record(node_id, record_lines)
        nodes.append(node)
        edges.extend(record_edges)
    return {"nodes": nodes, "edges": edges}


def graph_to_dot(graph: dict[str, Any]) -> str:
    """Serialize graph data as a directed Graphviz DOT graph with escaped labels."""
    def quote(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    output = ["digraph Dialogue {", "  rankdir=LR;", "  node [fontname=\"Helvetica\"];" ]
    for node in graph["nodes"]:
        label = node["id"]
        if node["text"]:
            label += "\n" + node["text"]
        shape = "diamond" if node["type"] == "choice" else "box"
        output.append("  %s [label=%s, shape=%s];" % (quote(node["id"]), quote(label), shape))
    for edge in graph["edges"]:
        output.append("  %s -> %s [label=%s];" % (quote(edge["from"]), quote(edge["to"]), quote(edge["text"])))
    output.append("}")
    return "\n".join(output) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 3:
        raise ValueError("usage: solution.py [script] [json-output] [dot-output]")
    input_path = Path(args[0]) if len(args) >= 1 else Path("/app/script.txt")
    json_path = Path(args[1]) if len(args) >= 2 else Path("/app/dialogue.json")
    dot_path = Path(args[2]) if len(args) >= 3 else Path("/app/dialogue.dot")
    graph = parse_script(input_path.read_text(encoding="utf-8"))
    json_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dot_path.write_text(graph_to_dot(graph), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
