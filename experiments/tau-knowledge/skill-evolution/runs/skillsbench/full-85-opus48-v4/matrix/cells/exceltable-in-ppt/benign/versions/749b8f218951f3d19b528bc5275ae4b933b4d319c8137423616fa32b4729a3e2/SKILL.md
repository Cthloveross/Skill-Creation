---
name: update-embedded-ppt-currency-rate
description: >
  Update one currency exchange rate inside an Excel workbook embedded in a
  PowerPoint (.pptx) file. The pptx shows a currency-rate matrix (each cell =
  rate from the row currency to the column currency) sourced from an embedded
  .xlsx part, and a text box on the slide states a new rate for one currency
  pair. The Skill discovers the embedded workbook and the text box at runtime,
  updates only the value cell for that pair (never overwriting formula cells
  with hard-coded numbers), repackages every other part of the pptx unchanged,
  and writes the result to the requested output path (default
  /root/results.pptx). Use it for the exceltable-in-ppt task or any
  "edit the embedded Excel table in a slide" request.
---

# Update an embedded PowerPoint currency table

## What the task requires

Given `/root/input.pptx`:
1. Extract and read the embedded Excel workbook (the currency-rate matrix).
2. Read the slide text box to get the updated rate for one currency pair.
3. Update that pair in the embedded workbook. Keep formula cells as formulas
   (do NOT convert formulas to hard-coded values).
4. Save to `/root/results.pptx` with everything else unchanged.

Key facts (from the frozen background):
- A .pptx is a ZIP/OOXML package; the workbook lives as a separate part
  (typically `ppt/embeddings/*.xlsx`). Discover it at runtime; do not hard-code
  archive paths, sheet names, cell addresses, currency codes or row counts.
- Formula text and cached results are distinct. openpyxl preserves formula text
  but does not recalculate cached values; that is acceptable here because the
  requirement is to keep formulas, not to recompute other cells.
- Direction and units matter: the matrix convention is
  value[row_currency, col_currency] = rate from row to column. Interpret the
  text-box statement from its labels, not from numeric magnitude.
- A successful ZIP write is not proof of validity: reopen both the presentation
  and the embedded workbook and check relationship/structure integrity.

## How to run it

The entrypoint reads JSON on stdin and prints a JSON report on stdout.

```
cd /app/environment/skills/current
python3 scripts/update_rates.py <<'JSON'
{"pptx_in": "/root/input.pptx", "pptx_out": "/root/results.pptx"}
JSON
```

Input schema (all optional except that defaults point at the task files):
- `pptx_in`  (string, default `/root/input.pptx`)
- `pptx_out` (string, default `/root/results.pptx`)
- `override` (object, optional) force the pair/rate when auto-detection is
  ambiguous: `{"from": "USD", "to": "EUR", "rate": 0.85}`.

Output report fields:
- `embedding_part`      the embedded .xlsx part that was edited
- `sheet`               worksheet name
- `currencies`          currency codes discovered in the matrix
- `textbox_text`        the concatenated slide text used for detection
- `detected`            `{from, to, rate}` parsed from the text box
- `updated_cell`        e.g. `{"addr":"C2","from":"USD","to":"EUR","value":0.85}`
- `formulas_preserved`  `{before, after}` formula-cell counts (must be equal)
- `parts_preserved`     `{input, output}` package part counts (must be equal)
- `validation`          per-check booleans; `ok` is the overall result
- `written`             the output path

## How the executor completes the task

1. First inspect the file so you understand the actual layout:
   `python3 scripts/inspect.py <<<'{"pptx_in":"/root/input.pptx"}'`.
   This prints the embedded parts, each sheet's grid, and all slide text so you
   can confirm the matrix orientation and the text-box wording.
2. Run `scripts/update_rates.py`. Read `textbox_text` and `detected` in the
   report and confirm the parsed pair/rate match the human-readable statement
   and the matrix convention (row→column). If the wording uses an unusual
   direction (e.g. "EUR per USD") and the auto-detection looks wrong, rerun with
   an explicit `override`.
3. Confirm `validation.ok` is true: the output exists, the target cell now
   holds the new numeric rate, `formulas_preserved.before == after`, and
   `parts_preserved.input == output`.
4. The deliverable is `/root/results.pptx`. Rerunning the entrypoint must
   regenerate it from `/root/input.pptx`; it never depends on earlier workspace
   state.

## Interpretation rules used by the script

- The embedded workbook to edit is the one whose worksheet contains a currency
  matrix (3-letter codes appearing both across a header row and down a label
  column). If several embeddings exist, the first matching one is used.
- Currency codes are 3-letter alphabetic tokens that occur in the matrix.
- From the text box, the script finds the two matrix currency codes and the
  numeric value. Default direction: first code = source (row), second code =
  target (column), so `value[from, to] = rate` (matching "1 FROM = rate TO").
  If the word "per" separates the codes ("TO per FROM"), the direction is
  inverted accordingly.
- The script updates the direct cell `[from, to]` only if it is a value cell.
  If that cell is a formula, it instead writes the reciprocal into the
  `[to, from]` value cell (if that one is a value), so no formula is replaced.
  If both candidate cells are formulas it does not overwrite either and reports
  `validation.ok=false` so the executor can decide.

## Failure modes handled explicitly

- No embedded workbook / no currency matrix found: report lists what was found
  and sets `validation.ok=false` (does not write a bogus output).
- Text box has no detectable pair or rate: report says so; supply `override`.
- Ambiguous number or multiple pairs: all candidates are reported; use
  `override` to disambiguate.
- The script preserves every other package part byte-for-byte and only replaces
  the single embedded .xlsx, so unrelated slides, media, relationships and
  document properties stay unchanged.
