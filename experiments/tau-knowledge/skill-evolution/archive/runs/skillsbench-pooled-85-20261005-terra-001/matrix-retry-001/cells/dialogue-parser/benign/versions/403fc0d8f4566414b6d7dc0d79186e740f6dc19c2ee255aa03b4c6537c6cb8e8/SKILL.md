---
name: dialogue-parser-artifact-builder
description: Create the required /app/solution.py dialogue parser and generate dialogue.json plus dialogue.dot from a bracket-record dialogue script. Use for the supplied dialogue-parser task.
---

# Dialogue parser artifact builder

Run the packaged builder from the Skill directory before finishing the task:

```sh
python3 scripts/build.py
```

The builder copies the self-contained parser to `/app/solution.py`, reads `/app/script.txt`, and writes `/app/dialogue.json` and `/app/dialogue.dot`. It prints a JSON result listing the three artifact paths.

The generated `parse_script(text)` deliberately follows the public input grammar: each bracket-only header is one node; every source line containing `->` produces one edge using the text before the final arrow and its target after that arrow. It preserves authored record text, identifies numbered (`1.`) records as choices, and records a first-line speaker without removing that speaker's authored text. Targets are not converted into invented nodes, so an external `End` remains an edge target.

The generated JSON schema is exactly `{"nodes": [...], "edges": [...]}`. Node objects contain string `id`, `text`, `speaker`, and `type` fields; edge objects contain string `from`, `to`, and `text` fields. DOT uses JSON quoting for safe escaped labels and emits each graph node and transition.

`scripts/build.py` optionally accepts a JSON object on stdin with string overrides `input_path`, `solution_path`, `json_path`, and `dot_path`; defaults are the required `/app` paths. It emits `{"ok": true, "paths": [...]}` on success or `{"ok": false, "error": "..."}` and a nonzero status on failure.
