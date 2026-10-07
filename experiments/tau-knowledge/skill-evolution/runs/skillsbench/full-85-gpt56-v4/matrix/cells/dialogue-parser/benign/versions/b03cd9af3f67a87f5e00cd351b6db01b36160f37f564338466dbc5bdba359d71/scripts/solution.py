#!/usr/bin/env python3
"""Parser and renderer for simple bracket-record branching dialogue scripts."""
from __future__ import annotations

import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

# A header must occupy the whole nonblank line. This intentionally does not
# mistake an inline choice annotation such as "[Lie] text" for a record.
HEADER_RE = re.compile(r"^\s*\[([^\]\r\n]+)\]\s*$")
CHOICE_RE = re.compile(r"^\s*(?:(?:\d+|[A-Za-z])[.)]|[-*+])\s+(.*)$")
SPEAKER_RE = re.compile(r"^\s*([^:\r\n]+?)\s*:\s*(.*)$")
TERMINALS = {"end", "exit", "quit", "terminal", "gameover", "game_over", "the end"}


def _clean_target(value: str) -> str:
    """Normalize just syntactic target decoration, retaining meaningful ID text."""
    value = value.strip().rstrip(";")
    if len(value) >= 2 and ((value[0], value[-1]) in {("[", "]"), ('"', '"'), ("'", "'")}):
        value = value[1:-1].strip()
    return value


def _split_transition(line: str) -> tuple[str, str | None]:
    """Return source text and target. The final arrow is the transition syntax."""
    if "->" not in line:
        return line.strip(), None
    left, right = line.rsplit("->", 1)
    target = _clean_target(right)
    # An empty right side is content, not a valid transition.
    if not target:
        return line.strip(), None
    return left.strip(), target


def _remove_speaker(text: str) -> tuple[str, str]:
    match = SPEAKER_RE.match(text)
    if not match:
        return "", text.strip()
    return match.group(1).strip(), match.group(2).strip()


def parse_script(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse text into {nodes: [...], edges: [...]} without creating target nodes.

    Repeated headers are coalesced into their first declared node so the output
    never contains duplicate IDs. Transition lines remain in source order.
    """
    records: list[tuple[str, list[str]]] = []
    by_id: dict[str, int] = {}
    current: list[str] | None = None

    for raw in text.splitlines():
        header = HEADER_RE.match(raw)
        if header:
            node_id = header.group(1).strip()
            if not node_id:
                raise ValueError("record header has an empty ID")
            if node_id in by_id:
                current = records[by_id[node_id]][1]
            else:
                current = []
                by_id[node_id] = len(records)
                records.append((node_id, current))
            continue
        if current is not None:
            current.append(raw)
        elif raw.strip():
            raise ValueError("content was found before the first [RecordId] header")

    if not records:
        raise ValueError("no [RecordId] headers found")

    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    for node_id, raw_lines in records:
        # Ignore blank separator lines, but retain all nonblank dialogue lines.
        useful = [line.strip() for line in raw_lines if line.strip()]
        parsed: list[tuple[bool, str, str | None]] = []
        for line in useful:
            source, target = _split_transition(line)
            choice_match = CHOICE_RE.match(source)
            if choice_match:
                parsed.append((True, choice_match.group(1).strip(), target))
            else:
                parsed.append((False, source.strip(), target))

        is_choice = any(item[0] for item in parsed)
        speaker = ""
        text_lines: list[str] = []
        for marked_choice, source, target in parsed:
            if is_choice:
                # Choice records may have annotations; retain them as text.
                visible = source
            else:
                line_speaker, visible = _remove_speaker(source)
                if not speaker and line_speaker:
                    speaker = line_speaker
            if visible:
                text_lines.append(visible)
            if target is not None:
                edge_text = visible
                edges.append({"from": node_id, "to": target, "text": edge_text})

        nodes.append({
            "id": node_id,
            "text": "\n".join(text_lines),
            "speaker": "" if is_choice else speaker,
            "type": "choice" if is_choice else "line",
        })

    return {"nodes": nodes, "edges": edges}


def _is_terminal(target: str) -> bool:
    return target.strip().casefold() in TERMINALS


def validate_graph(graph: dict[str, Any]) -> None:
    """Validate schema, references, and reachability without inventing nodes."""
    if set(graph) != {"nodes", "edges"}:
        raise ValueError("graph must contain exactly nodes and edges")
    nodes = graph["nodes"]
    edges = graph["edges"]
    if not isinstance(nodes, list) or not isinstance(edges, list) or not nodes:
        raise ValueError("graph needs a nonempty nodes list and an edges list")

    ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "text", "speaker", "type"}:
            raise ValueError("each node must have id, text, speaker, and type")
        if not all(isinstance(node[key], str) for key in node):
            raise ValueError("node fields must be strings")
        if not node["id"] or node["id"] in ids:
            raise ValueError("node IDs must be nonempty and unique")
        if node["type"] not in {"line", "choice"}:
            raise ValueError("node type must be line or choice")
        ids.add(node["id"])

    adjacency = {node_id: [] for node_id in ids}
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"from", "to", "text"}:
            raise ValueError("each edge must have from, to, and text")
        if not all(isinstance(edge[key], str) for key in edge):
            raise ValueError("edge fields must be strings")
        if edge["from"] not in ids:
            raise ValueError(f"edge source is not declared: {edge['from']}")
        if edge["to"] in ids:
            adjacency[edge["from"]].append(edge["to"])
        elif not _is_terminal(edge["to"]):
            raise ValueError(f"edge target is not declared or terminal: {edge['to']}")

    root = nodes[0]["id"]
    seen = {root}
    queue: deque[str] = deque([root])
    while queue:
        source = queue.popleft()
        for target in adjacency[source]:
            if target not in seen:
                seen.add(target)
                queue.append(target)
    missing = [node["id"] for node in nodes if node["id"] not in seen]
    if missing:
        raise ValueError("unreachable declared node(s): " + ", ".join(missing))


def _dot_quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def to_dot(graph: dict[str, list[dict[str, str]]]) -> str:
    """Serialize graph in DOT with safely quoted IDs and labels."""
    lines = ["digraph Dialogue {", "  rankdir=LR;", "  node [shape=box];"]
    for node in graph["nodes"]:
        label_parts = [node["id"], node["type"]]
        if node["speaker"]:
            label_parts.append(node["speaker"] + ":")
        if node["text"]:
            label_parts.append(node["text"])
        lines.append(f"  {_dot_quote(node['id'])} [label={_dot_quote(chr(10).join(label_parts))}];")
    for edge in graph["edges"]:
        suffix = f" [label={_dot_quote(edge['text'])}]" if edge["text"] else ""
        lines.append(f"  {_dot_quote(edge['from'])} -> {_dot_quote(edge['to'])}{suffix};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_outputs(graph: dict[str, list[dict[str, str]]], json_path: str | Path, dot_path: str | Path) -> None:
    """Write validated JSON and DOT files using UTF-8."""
    validate_graph(graph)
    json_file = Path(json_path)
    dot_file = Path(dot_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    dot_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dot_file.write_text(to_dot(graph), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in {1, 3}:
        print("usage: solution.py SCRIPT [DIALOGUE_JSON DIALOGUE_DOT]", file=sys.stderr)
        return 2
    script_path = Path(args[0])
    json_path = Path(args[1]) if len(args) == 3 else Path("dialogue.json")
    dot_path = Path(args[2]) if len(args) == 3 else Path("dialogue.dot")
    try:
        graph = parse_script(script_path.read_text(encoding="utf-8"))
        write_outputs(graph, json_path, dot_path)
    except Exception as exc:
        print(f"dialogue parser error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
