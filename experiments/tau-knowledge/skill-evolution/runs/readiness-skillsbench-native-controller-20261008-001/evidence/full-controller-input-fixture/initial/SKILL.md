---
name: current
description: Parse bracket-delimited dialogue scripts into validated JSON directed graphs and Graphviz DOT, exporting an importable solution.py with parse_script(text).
---

# Dialogue graph parser

## Contract and prerequisites
Use this skill for text scripts whose records start with standalone `[Identifier]` headers, whose dialogue uses `Speaker: text`, whose numbered choices use `1. text` (or `1) text`), and whose transitions end with `-> Target`. The task requires `/app/solution.py`, `/app/dialogue.json`, and `/app/dialogue.dot`. The exported module must expose `parse_script(text: str)` returning `{"nodes": [...], "edges": [...]}`. Use Python 3.12 and its standard library; Graphviz installation and network access are unnecessary.

Before execution, read the supplied task and inspect `/app/script.txt`, including its beginning, representative choice/line records, terminal records, and final record. Discover the actual headers, encoding, transitions, terminal conventions, and any instructions concerning field semantics. Do not substitute the illustrative dialogue or any background identifiers for runtime data. The supported default external terminal is `End`, because the public task explicitly names it. Other external sentinels require evidence in the supplied script or task and an explicit `terminals` configuration. A declared terminal remains an ordinary declared node. Do not exempt arbitrary dangling targets merely because they occur near EOF.

## Field semantics
One declared record produces one node, in source order. Node keys are exactly `id`, `text`, `speaker`, and `type`, all strings; type is `line` or `choice`. For dialogue, `speaker` is the prefix before the first colon, and `text` excludes that prefix and transition syntax. Unattributed narration has an empty speaker. Multiple dialogue lines with one speaker are joined with newlines; multiple distinct speakers in a single record are unsupported rather than silently conflated.

A numbered record is a choice node. Its text retains option numbering, tags, punctuation, and line order but excludes transition suffixes. Optional prompt lines retain their content after a speaker prefix. Each option transition becomes an edge whose text is the option label without numbering; tags such as `[Lie]` remain. Non-choice transitions have an empty edge text. All edges have exactly the string fields `from`, `to`, and `text`. Repeated references, cycles, and repeated edges are preserved. Duplicate record declarations are errors. Source wording is retained apart from structural syntax and leading/trailing whitespace.

`parse_script` parses syntax without demanding a closed graph, so partial snippets can be imported and parsed. The executable entrypoint additionally validates the complete graph: every source exists, every target is declared or an explicitly allowed external sentinel, and every declared node is reachable from the first declared node. It never adds an undeclared sentinel to the JSON node array.

## Execute and export
The packaged script reads one JSON object from stdin and emits one JSON object on stdout. Its input fields are:
- `input_path`: source script, default `/app/script.txt`.
- `encoding`: explicit Python text encoding, default `utf-8-sig` (also accepts ordinary UTF-8). Determine another encoding from runtime evidence if needed; never decode with replacement.
- `solution_path`: exported executable module, default `/app/solution.py`.
- `json_path`: graph artifact, default `/app/dialogue.json`.
- `dot_path`: visualization artifact, default `/app/dialogue.dot`.
- `terminals`: array of explicitly permitted external terminal IDs, default `["End"]`.

Run in the supplied writable task runtime, using the actual installed skill directory:

```sh
printf '%s\n' '{"input_path":"/app/script.txt"}' | python /app/environment/skills/current/scripts/solution.py
# Verify that the exported entrypoint itself regenerates and validates the artifacts:
printf '%s\n' '{"input_path":"/app/script.txt"}' | python /app/solution.py
```

Repeat the same nondefault configuration on the exported invocation when applicable. Successful stdout reports `ok: true`, artifact paths, node/edge counts, and verified reachability. Failure emits `ok: false` with a diagnostic and exits nonzero; do not treat stale artifacts as a successful result.

The script validates before writing, exports itself as the standalone `solution.py`, writes UTF-8 JSON and DOT atomically per file, rereads both, and checks JSON equality against a fresh parse plus exact DOT regeneration. DOT uses quoted, escaped identifiers and labels; external sentinels appear only as edge targets (Graphviz may display an implicit endpoint). No PNG is required.

## Verification and unsupported input
Inspect the generated outputs against representative source records: first and final node, a speaker line, numbered labels with tags, a repeated destination, and terminal transitions. Check that choice labels have not become invented nodes and that speaker/text separation has not lost punctuation. Import `/app/solution.py` and call `parse_script` on public snippets when useful; only the complete input must satisfy reachability and target validation. The exported entrypoint must regenerate both outputs, not merely import successfully.

Missing files, decoding failures, unrecognized pre-header text, duplicate IDs, malformed/empty transitions, ambiguous mixed speakers, unresolved targets, and unreachable records are explicit failures. Inspect the source and error before proceeding. Do not prune unreachable records, invent destinations, change source text, or relax validation to conceal an error. If the real format exceeds these conventions, implement a reusable, evidence-based extension in the executor's solution when task permissions allow it, preserving this schema and all validation obligations; otherwise report the unsupported syntax and do not claim completion. Creation does not execute or test this package.
