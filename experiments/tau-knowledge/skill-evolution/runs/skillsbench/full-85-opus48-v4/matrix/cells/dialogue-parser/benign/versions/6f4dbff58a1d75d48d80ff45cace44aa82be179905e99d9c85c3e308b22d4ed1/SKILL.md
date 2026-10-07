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
1. Read the task opening to confirm the input/output paths (defaults:
   `/app/script.txt`, `/app/dialogue.json`, `/app/dialogue.dot`). Inspect the
   actual script with the terminal before trusting assumptions:
   `sed -n '1,40p' /app/script.txt`.
2. Install the deliverable parser where validation imports it:
   `cp /app/environment/skills/current/scripts/solution.py /app/solution.py`
   (adjust the skill directory to the one reported in the environment).
3. Generate the artifacts by running the parser; it reads the script, writes
   both outputs, prints a JSON validation summary, and exits nonzero if any
   constraint fails:
   `cd /app && python solution.py`
   You may also pass explicit paths: `python solution.py <script> <json> <dot>`.
4. Confirm the deliverables exist and the parser is importable:
   `python -c "import solution,json; g=solution.parse_script(open('/app/script.txt').read()); print(len(g['nodes']),len(g['edges']))"`
5. Read `/app/dialogue.json` and spot-check that the first record is a `line`
   node, that `[NameChoice]`-style records are `choice` nodes with one edge per
   numbered option, that tags like `[Lie]` survive inside the option text, and
   that any `End` target has no fabricated node.

## Optional JSON wrapper
`scripts/run.py` reads a JSON object on stdin
`{"script_path": "/app/script.txt", "out_json": "/app/dialogue.json",
  "out_dot": "/app/dialogue.dot"}` (all keys optional; defaults as above),
writes the two files, and prints a JSON object on stdout:
`{"nodes": N, "edges": M, "errors": [...], "first_node": "..."}`.
An empty `errors` list means all three constraints passed.

## Handling surprises during execution
- If the script contains line kinds not covered (e.g. bare `-> Target`,
  narration without a speaker, or extra terminal names), adjust the small,
  explicit regexes / `TERMINALS` set in `scripts/solution.py` rather than
  rewriting the whole parser, then rerun step 3-5. A narration line (no `:`)
  keeps an empty speaker and contributes to the node text.
- If `validate()` reports unreachable nodes or missing targets, re-read the
  relevant records in the raw script to find the real cause (typo in a target,
  a header that should have been `End`, a dropped last block) before changing
  logic. Preserve each constraint's exact meaning; do not relax reachability to
  silence a missing-target error.
- Never hardcode this instance's node ids, counts, or expected graph into the
  Skill. Always parse the supplied `text` at runtime.
