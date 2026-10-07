# Dialogue script format notes

Derived only from the public task opening and the frozen background. No instance
ids, counts, or expected graph are encoded here.

## Records
- A header line matches `^\[([^\]]+)\]$` exactly (the whole line is a bracketed
  id). It starts a new node whose id is the bracket contents.
- All nonblank lines until the next header form that record's body.
- Blank lines are separators only.
- The final record must be processed (watch for off-by-one that drops the last
  block).

## Body line kinds
- Speaker/line: `Speaker: text [-> Target]`. The speaker is the text before the
  first `:` (ignored if that prefix looks like an arrow or a bracket tag). The
  node type is `line` when the record has no numbered options.
- Choice option: `N. text [-> Target]` or `N) text [-> Target]`. The option text
  is preserved verbatim, including inline tags such as `[Lie]` or `[Attack]`.
  A record containing numbered options is a `choice` node, and each option
  becomes an edge whose label is the option text.

## Edges
- `{"from": node_id, "to": target, "text": label}`.
- Choice edge label = option text; plain line transition label = "".
- `-> Target` always marks the transition target.

## Terminal sentinel
- `End` is the terminal "last node". Edges may point to `End` even though no
  `[End]` record is declared. Do not fabricate an `End` node unless it has a
  real header. Multiple paths may converge on `End`.

## Constraints to satisfy
1. All declared nodes reachable from the first declared node.
2. Every edge target is a declared node, except the terminal sentinel.
3. Multiple paths may lead to `End`.

## DOT serialization
- Escape `\\`, `"`, and newlines in labels.
- `line` nodes use shape `box`; `choice` nodes use shape `diamond` (cosmetic).
