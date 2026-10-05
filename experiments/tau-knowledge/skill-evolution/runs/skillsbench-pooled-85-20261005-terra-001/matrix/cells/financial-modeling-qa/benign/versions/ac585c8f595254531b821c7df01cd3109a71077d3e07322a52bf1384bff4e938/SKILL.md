---
name: rule-grounded-dice-match-analysis
description: Compute an odd-game versus even-game match-win difference from a labeled XLSX dice-game table. It discovers the table at runtime, carries merged/blank game labels forward, optimally assigns the 13 one-use scoring categories per game, and writes only the requested signed integer.
---

# Rule-grounded dice match analysis

Use this Skill for the supplied workbook/PDF task in which numbered dice games are scored under the supplied game rules, then games `1`/`2`, `3`/`4`, and so on are compared.

## Required artifacts

- XLSX workbook, normally `/root/data.xlsx`
- Authoritative PDF rules, normally `/root/background.pdf`
- Required output path, normally `/root/answer.txt`

The output file is an artifact: it must contain exactly the integer answer (optionally followed by one newline), not JSON, reasoning, or a score table.

## Method

1. Extract and read the supplied PDF before scoring. The game rules are authoritative; do not rely on a familiar game name alone.

   ```sh
   python scripts/extract_pdf_text.py <<'JSON'
   {"pdf":"/root/background.pdf"}
   JSON
   ```

2. Confirm that the PDF defines the conventional 13-category, five-die scorecard represented by the solver: upper faces one through six; three/four of a kind scoring total dice; full house 25; small/large straight 30/40; five of a kind 50; chance total dice; and a 35-point upper-section bonus at 63. Confirm that each of the 13 observed turns is assigned to a distinct category. If the PDF differs in any material way, do **not** use the standard solver unchanged; implement the documented rule difference and validate it against the PDF.

3. Inspect the workbook when needed. Header names, sheet names, and column positions are discovered rather than hardcoded.

   ```sh
   python scripts/inspect_xlsx.py <<'JSON'
   {"workbook":"/root/data.xlsx","max_rows":35,"max_columns":25}
   JSON
   ```

   In particular, inspect whether a game number is displayed once for a block or is stored in merged cells. A blank game cell beneath a prior valid game number denotes the same game; it is not a missing observation. Do not regroup records merely by arbitrary row position.

4. Run the end-to-end solver after the PDF confirmation:

   ```sh
   python scripts/solve_standard_dice_matches.py <<'JSON'
   {"workbook":"/root/data.xlsx","pdf":"/root/background.pdf","output":"/root/answer.txt"}
   JSON
   ```

   Stdout is a JSON audit report. Only the requested output path receives the scalar answer.

## Solver input and output schema

`solve_standard_dice_matches.py` receives one JSON object on stdin:

- `workbook` (required string): XLSX path.
- `output` (required string): destination answer-file path.
- `pdf` (optional string): PDF path. If provided, its extractable text must contain dice and score/scoring context.

It emits JSON with `answer`, `player1_wins`, `player2_wins`, `ties`, `matches`, selected table metadata, and per-match game scores. It writes `str(answer) + "\\n"` to `output`.

The solver searches the first 40 rows of every sheet for a labeled game identifier plus five labeled die/dice fields (or five labeled roll fields). It accepts common normalized game labels such as `Game Number`, `Game ID`, and `Game`, and die labels containing both `die`/`dice` and a number. It parses only rows with all five valid integer dice in `[1, 6]`, carries the most recent valid game identifier forward through blank game cells, and requires exactly 13 turns for every game.

For each game, dynamic programming maximizes the total score over all one-use assignments of the 13 categories, including the upper bonus. This is necessary because scoring every roll greedily can give a nonoptimal game total. Games must be consecutive starting at 1 and have an even final count. Tied game totals award no match to either player, as the requested quantity counts wins only.

## Validation and failure behavior

Before accepting the result, check the audit report and ensure:

- the selected table has one game-ID field and exactly five dice fields;
- every selected game has exactly 13 valid turns;
- the IDs are exactly `1..N` for an even `N`;
- each category is used once per game;
- each match is odd game versus its following even game; and
- `answer == player1_wins - player2_wins`.

Scripts fail with a JSON error instead of inventing an answer if a file is unavailable, PDF text cannot be checked, no unambiguous complete table is found, dice are invalid, a game is incomplete, or pairing is impossible. Such a failure requires artifact inspection or a rule-specific extension, not guessed values.
