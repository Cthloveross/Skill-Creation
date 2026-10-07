---
name: dice-workbook-match-analysis
description: Analyze a rule-defined dice-game workbook and compute the difference between wins by odd-numbered and even-numbered games. Use when a PDF supplies authoritative scoring rules and an XLSX supplies many game records.
---

# Dice workbook match analysis

Use this Skill for tasks in which a PDF defines how dice observations are scored and an XLSX contains numbered games to be paired as odd-versus-following-even games. The PDF and workbook structure are runtime inputs; do not assume sheet names, headers, row offsets, category names, tie rules, or an existing standard-game scoring convention.

## Packaged programs

All programs read one JSON object from standard input and emit one JSON object to standard output.

- `scripts/extract_pdf_text.py` extracts embedded text from every PDF page and reports coverage. Input: `{"pdf_path":"/path/rules.pdf"}`. Its `pages` result is the source for deriving the actual scoring and tie rules. A `page_count` with blank or near-empty page text is a warning that visual inspection or OCR may be necessary; do not silently treat a scanned PDF as having no rules.
- `scripts/inspect_workbook.py` inventories workbook sheets, dimensions, merged ranges, hidden row/column counts, formula counts, candidate header rows, and representative nonblank rows. Input: `{"xlsx_path":"/path/data.xlsx","sample_rows":8}`. This is discovery only and never changes the workbook.
- `scripts/solve_dice_matches.py` reads the XLSX according to an explicit, runtime-created mapping, applies either supplied scores or PDF-derived category rules, pairs games, and optionally writes the requested answer file. Its input schema is described below.

## Procedure

1. Extract all pages of the rule PDF. Read the extracted rules, including the number of dice per observation, all permitted score categories, whether a category can be reused, whether every observation must receive a category, the game-total rule, and how ties are treated. The PDF is authoritative over familiar game variants.
2. Inspect the workbook before choosing a sheet or cell coordinates. Locate the actual header row from labels and inspect whether the data has one row per game or multiple round rows per game. Account for formulas, hidden rows, blanks, and type formats. Preserve source game identifiers while converting them to positive integer game numbers only after validating that conversion.
3. Create a temporary JSON solver configuration based on the discovered structure. Do not place instance values, game IDs, or a computed answer into this Skill. Use either `workbook` mode or explicit `games` mode described below.
4. Run `solve_dice_matches.py`. It validates duplicate game numbers, incomplete odd/even pairs, invalid die faces, missing fields, and ambiguous formula cells. Resolve a validation error from the input evidence rather than guessing a missing result.
5. Inspect the JSON result: it includes game totals and per-pair winners so the aggregate can be reconciled. Confirm every relevant game was included exactly once, score assignments obey the configured category-use rule, and `player1_wins - player2_wins` equals `difference`.
6. For a task requiring `/root/answer.txt`, set `answer_path` to that exact path. The solver writes only the decimal integer and a final newline to that file. Reopen it or use a byte-level check to confirm that no explanatory prose was written.

## Solver input schema

The common fields are:

```json
{
  "answer_path": "/requested/output.txt",
  "tie_policy": "neither",
  "score_epsilon": 0,
  "workbook": { ... },
  "rules": { ... }
}
```

`tie_policy` must be one of `neither`, `player1`, or `player2`, and must come from the task or PDF. `score_epsilon` is normally zero and should be nonzero only when source rules justify tolerance.

### Workbook mode

`workbook` has these fields:

- `path`: XLSX path.
- `sheet`: exact worksheet name, or omit only when the workbook has one applicable sheet.
- `header_row`: one-based header row number discovered during inspection.
- `game_column`: header text for the game number column.
- `dice_columns`: ordered list of header texts for the dice fields. Use this when scores must be calculated from dice.
- `score_column`: header text containing an already-authoritative final game score. Use this instead of `dice_columns` only when the PDF/workbook establishes that it is the score to compare.
- `round_column` (optional): header text identifying an observation within a game. Without it, sheet order is used for the observations within each game.
- `include_hidden` (optional, default `true`): whether hidden worksheet rows are records. Set this from the workbook/task evidence, not preference.

Header matching is whitespace-, case-, punctuation-, and newline-insensitive, but a normalized match must still be unique. Blank data rows are ignored. Formula cells in needed fields are rejected because `openpyxl` does not calculate formulas reliably; use an evidenced cached/static source or calculate it with an appropriate spreadsheet engine first.

### Explicit-games mode

For a non-workbook source, use `games` instead of `workbook`:

```json
{
  "games": [
    {"id": 1, "score": 0},
    {"id": 2, "rolls": [[1, 2, 3, 4, 5]]}
  ]
}
```

This illustrates structure only, not scoring assumptions. A game must have exactly one of `score` or `rolls`; `rolls` is a list of ordered die-value lists.

### Rules mode for calculated scores

When observations need scoring, supply `rules` with a `categories` list and optional `faces`, `assignment`, and `allow_yahtzee_as_full_house`:

```json
{
  "faces": [1, 2, 3, 4, 5, 6],
  "assignment": "distinct_category_per_roll",
  "allow_yahtzee_as_full_house": false,
  "categories": [
    {"name": "...", "kind": "upper", "face": 1},
    {"name": "...", "kind": "chance"},
    {"name": "...", "kind": "n_of_kind", "n": 3, "score_mode": "sum"},
    {"name": "...", "kind": "n_of_kind", "n": 4, "score_mode": "fixed", "score": 0},
    {"name": "...", "kind": "full_house", "score": 0},
    {"name": "...", "kind": "straight", "length": 4, "score": 0},
    {"name": "...", "kind": "exact_counts", "counts": [2, 3], "score": 0}
  ]
}
```

Supported kinds are `upper` (sum dice equal to `face`), `chance` (sum all dice), `n_of_kind` (at least `n`, with `score_mode` `sum` or `fixed`), `full_house` (fixed score for counts 2 and 3), `straight` (fixed score for a consecutive distinct run of `length`), and `exact_counts` (fixed score when nonzero multiplicities equal `counts`). A failed condition scores zero. For `distinct_category_per_roll`, the solver finds the maximum total joint assignment with each category used at most once, rather than greedily selecting a category per roll. It requires no more rolls than categories. This model is appropriate only if the supplied rules actually impose that limitation.

If the PDF uses a scoring mechanic outside these kinds, do not approximate it. Derive the score transparently from the PDF and pass authoritative game scores through `score_column`/`score`, or extend the packaged scorer with a documented, testable rule implementation before executing it.

The solver requires game IDs to be consecutive positive integers in pairs `(1,2), (3,4), ...`; this detects omitted games instead of accidentally shifting all later pairings. It reports the winner under the requested odd/even-player convention and writes the final count difference only after all validation succeeds.

## Example invocation

Create a runtime JSON configuration after source inspection, then run:

```sh
python3 scripts/solve_dice_matches.py < /path/runtime-config.json
```

Use the returned `pair_results`, `game_scores`, `player1_wins`, and `player2_wins` as the audit trail. The requested artifact itself is produced only by `answer_path`.
