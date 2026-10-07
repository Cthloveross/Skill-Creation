---
name: dialogue-script-to-graph
description: >
  Parse a branching dialogue script (plain-text file with [NodeId] record
  headers, Speaker lines, and numbered choice options using '-> Target'
  transitions) into a validated JSON graph {"nodes":[...],"edges":[...]} and a
  GraphViz DOT visualization. Use for tasks that must implement
  `parse_script(text)` in solution.py and emit dialogue.json / dialogue.dot,
  where records are nodes, transitions are edges, and a terminal sentinel
  ('End') stays an edge target rather than a node.
---

# Dialogue Script -> Graph Skill

## When to use
Use when the task supplies a dialogue text file (default `/app/script.txt`) and
asks for:
1. a parser module `solution.py` exposing `def parse_script(text: str)` that
   returns a dict `{"nodes": [...], "edges": [...]}`;
2. an output JSON graph (default `/app/dialogue.json`);
3. a DOT visualization (default `/app/dialogue.dot`).

## Input format (as given by the task)
Records begin with a header line that is *only* `[NodeId]`. Following nonblank
lines belong to that record until the next header. Two line kinds appear:

- Line node body: `Speaker: text -> Target`
  (speaker is the text before the first `:`; `-> Target` is the transition).
- Choice node body: numbered options, e.g.
  `1. I am Sir Aldric, Knight of the Realm. -> KnightPath`
  `3. [Lie] I'm a merchant with important goods. -> MerchantPath`
  Inline bracket tags such as `[Lie]`/`[Attack]` are part of the option text and
  must be preserved, not treated as headers (headers are a bracketed id that
  fills the whole line).

## Modeling rules (from the frozen background)
- Records are **nodes**; transitions are **edges**.
- Node fields: `id`, `text`, `speaker`, `type` where `type` is `"line"` (no
  numbered options) or `"choice"` (has numbered options).
- Edge fields: `{"from": id, "to": target, "text": label}`. For choices the label
  is the full option text (tags preserved); for a plain line transition the
  label is `""`.
- A transition target may be the terminal sentinel `End`. **Do not** invent a
  node for `End` unless it is declared with its own `[End]` header. Keep it as an
  edge target.
- Avoid duplicate nodes: only headers create nodes; a target that names an
  existing node is just an edge. If an id is declared twice, keep one node.
- Process the final record (do not drop the last block) and preserve source text
  verbatim in `text` and edge labels.
- Escape labels (`\\`, `"`, newline) when serializing DOT.

## Validation constraints (must hold for the produced graph)
1. Every declared node is reachable from the first declared node (BFS over
   edges, restricted to declared targets).
2. Every edge target resolves to a declared node, except the terminal sentinel
   `End` (the "last node"), which may be a target without a declared node.
3. Multiple paths may lead to `End`.

## How to execute the task
IMPORTANT: a complete, already-tested parser is shipped in this Skill at
`scripts/solution.py`. **Do not reimplement it** — just run it. It exposes
`parse_script(text)` and, when executed, self-installs the deliverable to
`/app/solution.py` and writes both output files.

Run exactly one command (no stdin, cannot block). Use this Skill's own
directory; `$SKILL_DIR` is the folder that contains this SKILL.md (default
`/app/environment/skills/current`):

```
python "$SKILL_DIR/scripts/solution.py"
```

That single command:
- copies `scripts/solution.py` to `/app/solution.py` so `import solution`
  works for the validator (regardless of the current directory);
- parses `/app/script.txt`;
- writes `/app/dialogue.json` and `/app/dialogue.dot`;
- prints a one-line JSON summary `{"nodes":N,"edges":M,"first_node":...,
  "errors":[...]}` and exits nonzero if any of the three constraints fails
  (empty `"errors"` == success).

Optional explicit paths (positional, no stdin):
`python "$SKILL_DIR/scripts/solution.py" <script> <out_json> <out_dot>`.
`scripts/run.py` is an equivalent thin wrapper with the same arguments.

Then confirm the deliverable is importable and the artifacts exist:
```
cd /app && python -c "import solution; g=solution.parse_script(open('/app/script.txt').read()); print(len(g['nodes']), len(g['edges']))"
ls -l /app/solution.py /app/dialogue.json /app/dialogue.dot
```
Spot-check `/app/dialogue.json`: the first record is a `line` node; a
`[NameChoice]`-style record is a `choice` node with one edge per numbered
option; inline tags like `[Lie]` survive inside the option text; and any `End`
target has no fabricated node.

## Helper interfaces
- `scripts/solution.py` (the deliverable, also runnable):
  - `parse_script(text: str) -> {"nodes": [...], "edges": [...]}` — pure, no I/O.
  - `validate(graph) -> [error strings]` — empty list means all three
    constraints hold.
  - `to_dot(graph) -> str` — GraphViz DOT with escaped labels.
  - `build_outputs(script_path, out_json, out_dot)` — reads the script, writes
    both files, returns the graph.
  - `install_self(dst="/app/solution.py")` — copies this module to the import
    path the validator uses.
  - CLI: `python solution.py [script_path] [out_json] [out_dot]` (no stdin).
- `scripts/run.py` — thin wrapper: `python run.py [script_path] [out_json]
  [out_dot]` delegating to `solution.main` (no stdin, cannot block).

## Handling surprises during execution
- If the script contains line kinds not covered (e.g. bare `-> Target`,
  narration without a speaker, or extra terminal names), adjust the small,
  explicit regexes / `TERMINALS` set in `scripts/solution.py` rather than
  rewriting the whole parser, then rerun the command plus the import/spot-check above. A narration line (no `:`)
  keeps an empty speaker and contributes to the node text.
- If `validate()` reports unreachable nodes or missing targets, re-read the
  relevant records in the raw script to find the real cause (typo in a target,
  a header that should have been `End`, a dropped last block) before changing
  logic. Preserve each constraint's exact meaning; do not relax reachability to
  silence a missing-target error.
- Never hardcode this instance's node ids, counts, or expected graph into the
  Skill. Always parse the supplied `text` at runtime.
