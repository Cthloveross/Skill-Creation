---
name: rule-grounded-dice-match-analysis
description: Analyze an XLSX file of numbered dice games using the authoritative supplied PDF rules, optimize any per-game one-use scoring-category assignment, pair odd games against following even games, and write the requested win-difference scalar. Use when the workbook layout and exact dice scoring rules must be determined at runtime rather than assumed.
---

# Rule-grounded dice match analysis

## Purpose

This Skill produces the requested scalar:

`(matches won by Player 1) - (matches won by Player 2)`

where Player 1 owns odd-numbered games and Player 2 owns even-numbered games. It deliberately does not embed any workbook-specific columns, rules, game IDs, tie policy, or answer.

## Required runtime inputs

- The XLSX workbook (normally `/root/data.xlsx`).
- The authoritative PDF rule document (normally `/root/background.pdf`).
- The task wording, which specifies pairing and required output path.

The executor must read the PDF before selecting a scoring specification. Familiar dice-game rules must not be substituted for the supplied document.

## Procedure

1. Extract the PDF text:
   ```
   python scripts/extract_pdf_text.py <<'JSON'
   {"pdf":"/root/background.pdf"}
   JSON
   ```
   Read the resulting text and record, exactly as stated by the PDF:
   - dice domain and number of dice per observation;
   - all scoring categories and their point functions;
   - whether a category can be used once per game;
   - whether every observation must receive a category;
   - bonuses, if any;
   - treatment of ties and incomplete games, if stated.

2. Inspect the workbook without assuming sheet names, row positions, or column letters:
   ```
   python scripts/inspect_xlsx.py <<'JSON'
   {"workbook":"/root/data.xlsx","max_rows":30,"max_columns":30}
   JSON
   ```
   Use headings and observed types to identify the game identifier, any turn/observation identifier, and every die column. Confirm whether one worksheet row is one observation and repeated game IDs form games. Check formulas with no cached result rather than silently treating them as blanks.

3. Translate the PDF rules into the documented JSON scoring specification accepted by `scripts/solve_dice_matches.py`. The specification is an explicit audit artifact; do not use fixed column letters or a remembered category list. The included solver supports common category functions and a threshold bonus. If the authoritative rules contain a construct that the schema cannot represent (for example rerolls, inter-game carryover, a non-threshold conditional bonus, or a global constraint), stop and implement a small rule-specific extension with tests rather than approximating it.

4. Run the solver. A representative invocation (illustrative names only) is:
   ```
   python scripts/solve_dice_matches.py <<'JSON'
   {
     "workbook":"/root/data.xlsx",
     "output":"/root/answer.txt",
     "spec": {
       "sheet":"<discovered sheet name>",
       "header_row":1,
       "game_id_column":"<discovered game heading>",
       "roll_columns":["<die heading 1>","<die heading 2>"],
       "dice_domain":[1,6],
       "categories":[
         {"name":"ones","kind":"face_sum","face":1},
         {"name":"chance","kind":"sum"}
       ],
       "category_usage":"at_most_once",
       "require_every_observation_assigned":true,
       "pairing":{"mode":"odd_vs_next_even","start_id":1,"require_contiguous":true},
       "ties":"no_win",
       "include_details":true
     }
   }
   JSON
   ```

5. Validate before delivering the result:
   - all populated data rows have valid, integral game IDs and dice in the PDF's domain;
   - every game has the required number of observations and an assignment satisfying the category-use policy;
   - every expected odd/even pair exists, with no positional regrouping;
   - no category is reused in a game when use is limited;
   - game scores are recomputable from the emitted selected-category detail;
   - `player1_wins - player2_wins` equals the number placed in the output file.

`solve_dice_matches.py` writes `/root/answer.txt` (or the supplied output path) containing only the signed integer and a trailing newline. Its stdout is JSON audit output and must not be copied into the answer file.

## Solver input schema

The solver receives one JSON object on stdin:

- `workbook` (string): XLSX path.
- `output` (string): answer-file path.
- `spec` (object):
  - `sheet` (string), `header_row` (1-based integer), `game_id_column` (exact heading), and `roll_columns` (exact headings) are required.
  - `dice_domain`: `[minimum, maximum]`, required.
  - `categories`: nonempty list of category objects, described below.
  - `category_usage`: `"at_most_once"` or `"exactly_once"`.
  - `require_every_observation_assigned`: boolean. If false, an observation may be left unscored; use this only if the PDF explicitly permits it.
  - `pairing`: `{ "mode":"odd_vs_next_even", "start_id":<integer>, "require_contiguous":<boolean> }`. The supplied question calls for this pairing mode.
  - `ties`: `"no_win"`, `"player1"`, `"player2"`, or `"error"`; choose only from an applicable task instruction or rule.
  - `expected_observations_per_game` (optional positive integer) rejects incomplete groups.
  - `bonuses` (optional list): threshold bonuses of the form `{ "name":..., "category_names":[...], "threshold":number, "points":number }`. A bonus is added once when the selected category scores named in `category_names` total at least `threshold`.
  - `include_details` (optional boolean) emits selected categories and component scores for each game.

A category has a unique `name`, a `kind`, and kind-specific properties:

- `face_sum`: `face` (integer); scores the sum of dice matching that face.
- `sum`: scores all dice.
- `fixed`: `points` (number); unconditional fixed score.
- `n_of_kind`: `n` (integer), optional `exact` (boolean), and `score` equal to `"sum"` or `"fixed"`; fixed scoring also requires `points`.
- `full_house`: optional `score` (`"fixed"` default or `"sum"`) and `points` for fixed scoring. It recognizes exactly one pair plus one triple.
- `straight`: `length` (integer), optional `exact` (boolean), and `score`/`points` as above. A straight is a consecutive run among distinct dice; `exact:true` requires exactly `length` distinct values.
- `custom_table`: `table`, mapping canonical comma-separated sorted dice (for example `"1,2,3,4,5"`) to numeric points. Unlisted rolls score zero.

The solver uses dynamic programming across observations, retaining category masks and bonus-relevant subtotals. This optimizes the joint assignment rather than greedily taking each observation's locally highest category.

## Failure behavior

The scripts emit a JSON error object and fail rather than inventing data if a PDF extractor is unavailable, the expected sheet/header is absent, a formula has no cached value, dice or IDs are invalid, a category is unsupported, assignments are impossible, pair IDs are missing, or an unresolved tie policy is requested. These conditions require inspection of the authoritative artifacts or a rule-specific solver extension.
