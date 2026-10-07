---
name: dialogue-script-graph-parser
description: Build a self-contained Python solution for tasks that convert bracket-headed branching dialogue scripts into validated JSON node/edge graphs and escaped Graphviz DOT visualizations. Use when the runtime supplies a dialogue text file and requires parse_script(text).
---

# Dialogue Script Graph Parser

## Deliverable procedure

1. Copy `references/solution.py.txt` to the required runtime location as `solution.py` (for this task, `/app/solution.py`). It is self-contained and exposes `parse_script(text: str)`.
2. Run the solution as a program from the task work directory. Its defaults read `/app/script.txt` and write `/app/dialogue.json` and `/app/dialogue.dot`; command-line paths may also be supplied in this order: input, JSON output, DOT output.
3. Validate the generated JSON before considering the artifact complete. For example, pass `{"graph": <contents of dialogue.json>}` to `scripts/validate_graph.py`. A valid result has `valid: true`.
4. If the supplied format materially differs from bracket record headers and `->` transitions, inspect the script and adapt only the parsing patterns while retaining the required graph schema, terminal handling, and validation rules.

## Parsing model

- A bracket-only line such as `[SceneId]` starts a declared record and becomes one graph node. Record order defines the first/root node.
- Every `-> target` found in a record becomes an edge from that record's ID. The edge `text` is the source text before the arrow, with its source wording preserved.
- A record containing numbered or bullet-style options is a `choice`; other records are `line`. A `Speaker: dialogue` prefix supplies `speaker` and is removed from the line node's dialogue text.
- Preserve all dialogue fragments within a record, including the final record. Do not create a node for a repeated target or for an undeclared external `End` target.
- A target must resolve to a declared ID unless it is the conventional terminal `End` (case-insensitive) and no `End` record is declared. All declared nodes must be reachable from the first declared node. Reject duplicate IDs and malformed/unresolved graphs instead of silently inventing data.
- DOT output must quote/escape identifiers and labels. Use node shapes only as visualization metadata; JSON remains the authoritative graph.

## Interfaces

`parse_script(text)` returns exactly a dictionary shaped as:

```json
{"nodes":[{"id":"...","text":"...","speaker":"...","type":"line|choice"}],"edges":[{"from":"...","to":"...","text":"..."}]}
```

The validator reads JSON on stdin:

```json
{"graph":{"nodes":[],"edges":[]},"terminal_ids":["End"]}
```

and emits `{"valid": true|false, "errors": ["..."]}`. `terminal_ids` is optional and defaults to `End`.

The parser intentionally raises `ValueError` for an empty script, duplicate record IDs, missing nonterminal targets, and unreachable declared records. This makes an invalid source observable rather than producing a graph that falsely claims to meet the task constraints.
