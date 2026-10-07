# Recovery relationship catalogue & checklist

These are general spreadsheet-recovery relationships. Apply one only when a
label, header, or existing formula in the *current* workbook justifies it.

## Relationship forms
- **Total / component**: a labeled total equals the sum of its components, so a
  single missing component = total - sum(known components). Also a missing total
  = sum(components).
- **Share / percentage of total**: `share% = 100*part/total`; invert with
  `part = total*share%/100` or `total = 100*part/share%`.
- **Relative (year-over-year) change**: `g% = 100*(current-prev)/prev`; invert
  with `current = prev*(1+g%/100)` or `prev = current/(1+g%/100)` when prev!=0.
- **Compound annual growth (CAGR)**: for start a, end b over n equal intervals,
  `CAGR% = 100*((b/a)**(1/n)-1)`. Infer n from the labeled observations, not a
  calendar assumption.
- **Mean / average**: sum of the *included* observations divided by their count;
  which observations are included must come from labels/formulas.
- **Simple difference**: one labeled value minus another.
- **Repeated cross-sheet fact**: the same entity+period value appears on more
  than one sheet; a known copy fills the missing copy. Cross-sheet dependencies
  are not necessarily circular — one sheet may independently fix a value another
  sheet needs.

## Solving order
1. Fill variables whose inputs are all already known.
2. Add each recovered value to the known set; repeat.
3. For simultaneous linear constraints, solve the system (scripts/linsolve.py)
   rather than guessing. Non-linear relations: compute directly in Python.

## Precision
- Keep full float precision in intermediate steps.
- Choose rounding from the target cell's number format and neighboring values;
  round only at write time.
- A rounded percentage can map to several source values — disambiguate with an
  independent constraint. If evidence is insufficient for a unique value, do not
  invent one.
- Distinguish blank cells, formula errors, strings, and numbers; never let a
  textual placeholder participate in arithmetic.

## Verification checklist (run on the saved output)
- No targeted placeholder remains anywhere.
- Every inserted value satisfies all applicable independent constraints within
  the evidenced precision (totals, shares, changes, repeated cross-sheet facts).
- Inserted cells are numeric, with appropriate number formats.
- Sheet names, formulas, styles, merged ranges and unrelated cells are unchanged.
- The output path matches exactly what the task requested.
