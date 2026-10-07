# Execution checklist

1. Re-read the current public request; use its actual sandbox paths (do not hardcode).
2. `pdf_text.py` -> read ALL rule text. Record, in your own words:
   - how one game's score is computed from its observations;
   - whether each category/resource is used at most once per game (needs joint optimal
     assignment, not greedy);
   - any bonus thresholds and their effect;
   - the exact definition of "winning a match" and the tie policy;
   - the sign convention of the requested difference (Player 1 minus Player 2 here).
3. `xlsx_overview.py` -> map game id, round/dice columns, totals. Reconcile game count.
   Check blanks, formulas vs cached values, merged/hidden rows. Investigate any missing
   game before trusting the layout; never shift later games into an empty slot.
4. Score every game. If assignment is required, adapt `dice_scoring.py` CATEGORY_SCORERS
   to the PDF's real categories/points, then use `score` mode. Run `selfcheck` first.
   If the workbook already stores a correct total, verify it against the PDF on a few
   hand-checked games before using it directly.
5. Build the per-game score list and run `match_result.py` with the correct tie policy.
6. Write ONLY the integer difference to the requested answer file (default /root/answer.txt).
7. Validate: recompute from the intermediate table; confirm each game is in exactly one
   match; dice values within domain; no illegal category reuse; optimizer vs exhaustive
   agree on small cases.

## Common pitfalls
- Assuming a familiar dice game's rules instead of the PDF's.
- Fixed column letters / sheet names instead of discovered mapping.
- Greedy category picks when the optimum requires joint assignment.
- Wrong tie handling or wrong difference sign.
- Writing a labeled string instead of just the number.
