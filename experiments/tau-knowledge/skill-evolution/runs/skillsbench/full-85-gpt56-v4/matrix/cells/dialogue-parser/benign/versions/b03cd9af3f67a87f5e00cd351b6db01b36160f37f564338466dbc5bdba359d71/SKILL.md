---
name: dialogue-script-graph
version: 1.0.0
description: Install and run a reusable Python parser for bracket-record dialogue scripts, producing a validated JSON node/edge graph and escaped Graphviz DOT visualization. Use when a task supplies a dialogue text file and requires solution.py with parse_script(text).
---

# Dialogue Script Graph

Use this Skill for scripts whose declared dialogue records begin with a line of
form `[RecordId]`. Each declared record becomes exactly one graph node. Lines
inside a record may contain `-> Target`; numbered, lettered, or bulleted
transition lines are choices, while other records are dialogue lines.

## Deploy and run

The runtime input is normally `/app/script.txt`. Run the packaged launcher from
the Skill directory; it copies the required importable artifact to `/app` and
writes both requested outputs:

```sh
python scripts/install_and_run.py <<'JSON'
{"script_path":"/app/script.txt","solution_path":"/app/solution.py","json_path":"/app/dialogue.json","dot_path":"/app/dialogue.dot"}
JSON
```

The launcher reads one JSON object on stdin and emits one JSON status object on
stdout. All paths are optional and default to the paths above. It fails clearly
for a missing source file, malformed record structure, duplicate/empty IDs, an
unresolved nonterminal target, or an unreachable declared node.

`/app/solution.py` is the deliverable. It exposes:

```python
parse_script(text: str) -> dict
```

and may also be invoked directly as:

```sh
python /app/solution.py /app/script.txt /app/dialogue.json /app/dialogue.dot
```

## Output interpretation and validation

The JSON has only `nodes` and `edges`. Every node has string `id`, `text`,
`speaker`, and `type` (`line` or `choice`); every edge has string `from`, `to`,
and `text`. Source record order and transition order are retained. Dialogue
text excludes the speaker prefix and `-> target`; choice text excludes its
choice marker. Edge labels use that same source transition text.

Validation is deliberately performed over declared nodes only. A target named
`End` (case-insensitive, including common terminal spellings) may be an
external terminal target; it is retained as an edge target and is never added
to JSON nodes. If such an ID is declared, it is an ordinary node. All other
edge targets must resolve. Reachability begins at the first declared node and
allows cycles and multiple inbound edges. The DOT writer quotes and escapes all
identifiers and labels, including embedded quotes, backslashes, and newlines.

If a supplied dialect uses a different record header or transition delimiter,
do not fabricate nodes: adapt the parser’s header/transition recognizers while
preserving this schema and rerun the launcher.
