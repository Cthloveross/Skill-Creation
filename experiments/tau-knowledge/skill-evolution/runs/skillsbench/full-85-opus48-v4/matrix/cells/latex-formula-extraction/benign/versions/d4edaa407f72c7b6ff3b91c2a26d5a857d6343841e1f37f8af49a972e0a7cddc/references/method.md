# Method reference: display-formula extraction

## Display-mode vs inline
- Display-mode formulas occupy their own line, are centered or (in some journal
  styles) left-aligned within their column, and have vertical whitespace above
  and below. They may carry an equation number in the right margin.
- Inline formulas share a line with prose (same baseline) and must NOT be
  extracted. If a formula shares its line with words, it is inline.
- Not every page has display formulas; intro / conclusion / references usually
  have none.
- Robust detection combines signals: own line, no prose words on the line,
  presence of math symbols, vertical whitespace, optional margin number. Review
  ambiguous candidates against the rendered page; both omissions and extra
  non-formula lines make the result unfaithful.

## Two-column layouts
Many papers are two-column. Treat each column as an independent region; detect
the gutter (a vertical gap near the horizontal center with no text). Second-
column formulas may be centered differently, so judge centering relative to the
column, not the full page.

## PDF-to-LaTeX is lossy
PDF stores positioned glyphs, not source. Recovering LaTeX is reverse
engineering. The same rendering has many valid source strings
(`\frac`=`\dfrac` in display, `\sum_{i=1}^N`=`\sum_{i=1}^{N}`). You need
*rendering equivalence* with the PDF, not the exact original source. If a
renderer (MathJax, matplotlib mathtext) is available, use it to confirm a
candidate renders like the page.

## Cleaning rules (applied by clean_formula / clean_formula.py)
1. Remove `\tag{...}` and `\tag*{...}`.
2. Remove trailing equation numbers: `\quad (1)`, `\qquad (2.3)`, bare `(4)` at
   the end, etc. These are numbering artifacts, not math.
3. Remove a single trailing grammatical comma or period that belongs to the
   sentence, not the math.
4. Collapse runs of whitespace/newlines/tabs to single spaces (LaTeX ignores
   math-mode whitespace, so rendering is unchanged).
5. Never rename variables, reorder terms, simplify, or "improve" notation.

## Error correction scope
Correctable (append a fixed copy; keep the original too):
- Mismatched `\left`/`\right` delimiters.
- Misspelled LaTeX commands (`\alhpa`->`\alpha`, `\sinn`->`\sin`), confirmed
  against the page (watch out for legitimate custom macros).
- Missing grouping braces that change rendering (`x_ij`->`x_{ij}`).

Leave alone (NOT errors):
- Wrong physics/math (sign errors) that are visually intentional.
- Stylistic choices (`\cdot` vs `\times`, `\frac` vs `\dfrac`, delimiter sizes,
  `\displaystyle`).

## Delimiter groups for \left/\right (used by validate_brackets)
Every `\left X` must pair with a `\right Y` whose delimiter is in the SAME
group:
- paren `(` / `)`
- square `[` / `]`
- brace `\{` / `\}`
- angle `\langle` / `\rangle`  (multi-char commands -- easy to miss; cover them)
- vert `|` (both sides) and `\lvert` / `\rvert`
- Vert `\|` (both sides) and `\lVert` / `\rVert`
- ceil `\lceil` / `\rceil`, floor `\lfloor` / `\rfloor`
- dot `.` is the invisible one-sided delimiter and matches anything.

When fixing a mismatch there is no universal rule for which side to change;
infer the intended pair from repeated notation elsewhere, the group's
mathematical role, and the visible glyphs in the PDF. validate_brackets gives
both candidate rewrites (fix_match_close, fix_match_open); choose with the PDF.
When rewriting multiple delimiters in one string, apply replacements from the
end backward so earlier indices stay valid (the helper rewrites one at a time).

## Output layout (build_markdown / assemble.py)
- One formula per line, wrapped in `$$...$$`, no blank lines between formulas.
- No duplicate original lines (dedup on the cleaned content between `$$`).
- All ORIGINAL (cleaned) formulas first.
- Then a blank line.
- Then the CORRECTED copies, appended -- each fix is an ADDITIONAL line, never a
  replacement of its original.
- Default output file: `/root/latex_formula_extraction.md` (use the path the
  task specifies).

## Validation checklist before finishing
- Re-run assemble.py and confirm it regenerates identical file content.
- Every non-blank line matches `^\$\$.*\$\$$`.
- No duplicate original lines.
- Corrected lines appear only after all originals.
- No leftover `\tag`, trailing `,`/`.`, or `(n)` equation number.
- Count of display formulas matches what you see in the rendered pages (no
  inline formulas leaked in, none missed, including the second column).
