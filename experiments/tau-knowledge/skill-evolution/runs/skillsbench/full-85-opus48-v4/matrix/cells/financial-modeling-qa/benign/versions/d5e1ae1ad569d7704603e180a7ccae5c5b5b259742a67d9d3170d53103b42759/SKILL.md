---
name: rule-grounded-dice-spreadsheet-qa
description: >
  Answer a quantitative question that combines a supplied rule document (PDF) with a
  large spreadsheet (xlsx). Specialized for "dice game" scoring tasks where each game's
  score must be derived from authoritative rules, games are grouped into head-to-head
  matches, and the deliverable is a single number written to a text file. Use when the
  task hands you a background.pdf of rules plus a data.xlsx of per-game observations and
  asks for a win-count difference (e.g. matches won by Player 1 minus Player 2).
---

# Rule-Grounded Dice Spreadsheet QA

## What this task asks (current instance)
Inputs (verify actual sandbox paths from the public request at runtime; usually):
- `/root/background.pdf` – authoritative scoring rules for the game.
- `/root/data.xlsx` – large workbook with the per-game observations.

Question pattern: odd-numbered games belong to Player 1, even-numbered games to Player 2;
games are matched consecutively (game 1 vs 2, game 3 vs 4, ...). Report
`(matches won by Player 1) - (matches won by Player 2)` as a plain number written to
`/root/answer.txt` (number only, no label, no extra text).

The exact scoring formula, the meaning of "winning a match", tie handling, and the sign of
the difference MUST come from the supplied PDF and the instruction text — never from a
remembered variant of a dice game. The scripts below are tools; the executor must first
inspect the real files and confirm the rules before trusting any default.

## Method (do these in order)
1. **Confirm paths.** Re-read the current public request. Do not assume paths; use the
   `sandbox_paths` given for this instance.
2. **Extract the rules.** Run `scripts/pdf_text.py` to dump the PDF text. Read it. Write
   down, as a small testable function, how a single game's score is computed from its
   observations, whether categories/resources are used at most once per game (requiring a
   joint optimal assignment, not greedy picks), and any bonus thresholds.
3. **Discover the spreadsheet structure.** Run `scripts/xlsx_overview.py`. Identify: the
   sheet holding data, where game identifiers live, how many games there are, how the dice
   values / rounds are laid out, and whether a per-game total already exists. Map semantic
   fields to the discovered columns — do not assume column letters. Reconcile the game
   count and check for blanks, merged cells, formulas vs cached values, and hidden rows
   before aggregating. If one game appears missing, find the parsing cause; do not shift
   later games into its slot.
4. **Score each game.** Build an intermediate table: one row per game with its parsed
   inputs, rule-derived component scores, the chosen assignment, and the game total.
   - If the rules require assigning limited categories across the game's rounds, model the
     joint assignment. `scripts/dice_scoring.py` provides optimal max-weight assignment
     (DP over category subsets) plus a reference Yahtzee-style category library you can
     adapt to the PDF's actual categories/values. Only use these if the PDF matches; edit
     the category functions to the real rules otherwise.
   - If the workbook already stores a correct per-game total, you may read it directly, but
     confirm it matches the PDF rule on a few hand-checked games first.
5. **Form matches and count wins.** Feed the per-game scores to `scripts/match_result.py`,
   which pairs consecutive games (1v2, 3v4, ...), treats odd game numbers as Player 1 and
   even as Player 2, counts match wins, and returns the difference. Set the `tie` policy to
   match the instruction/rules (default: ties count for neither).
6. **Write the answer.** Write only the integer difference to `/root/answer.txt` (or the
   path the instruction gives). No trailing label.
7. **Validate.** Recompute the difference from the intermediate table; verify every game id
   appears in exactly one match, no category/resource is reused illegally within a game,
   accepted dice values lie in the rules' domain, and the exhaustive and optimized scorers
   agree on small synthetic cases (`scripts/dice_scoring.py` self-check mode).

## Scripts
All scripts read a JSON object on stdin and print a JSON object on stdout.

### scripts/pdf_text.py
Input: `{"pdf_path": "/root/background.pdf"}`
Output: `{"text": "...full extracted text...", "pages": N, "engine": "pdfplumber|pypdf"}`
Tries pdfplumber then pypdf/PyPDF2; if none installed and internet is allowed, prints the
pip command to run. Read the whole text before deciding the scoring rule.

### scripts/xlsx_overview.py
Input: `{"xlsx_path": "/root/data.xlsx", "sample_rows": 20}`
Output: sheet names, each sheet's dimensions, detected header row candidates (normalized
text), per-column inferred types, and a sample of the first rows (both cached values and
whether a cell is a formula). Use this to map fields; nothing is hardcoded.

### scripts/dice_scoring.py
Two modes via `{"mode": ...}`:
- `{"mode": "score", "rounds": [[d1..dk], ...], "categories": [name,...]}` returns the
  optimal max-total assignment of each round to a distinct category using DP over subsets
  (also an exhaustive solver for small cases, which must agree). Category scoring uses the
  reference library in the file — EDIT it to match the PDF's actual categories/points.
- `{"mode": "selfcheck"}` runs synthetic cases comparing exhaustive vs DP optima and
  reports agreement; use before trusting the optimizer.

### scripts/match_result.py
Input: `{"games": [{"number": int, "score": number}, ...], "tie": "none|p1|p2"}`
Pairs sorted games consecutively (lowest two, next two, ...). Odd game number => Player 1,
even => Player 2. Higher score wins that match. Output:
`{"p1_wins": a, "p2_wins": b, "ties": t, "matches": m, "difference": a-b}`.
The reported difference is Player 1 minus Player 2, matching the question's sign.

## Failure handling
- If the PDF text cannot be extracted, install a reader (internet is allowed) and retry; do
  not guess the rules.
- If the spreadsheet structure differs from any assumption, re-run the overview and remap;
  do not force-fit.
- If the supplied artifacts genuinely do not determine a value, stop and report rather than
  invent. Never copy a remembered answer.
