# Method reference: display-formula extraction and correction

Distilled from the task background. Use as a checklist while transcribing.

## Display vs inline
- Extract ONLY display-mode formulas: own line, visually separated, often an
  equation number in the right margin. Delimiters in source would be `$$...$$`,
  `\[...\]`, or `equation`/`align`/`gather` environments.
- Exclude inline math (`$...$`, `\(...\)`) embedded within a sentence/baseline.
- A page may have zero, one, or several. Intro/conclusion/references usually none.
- The rendered page layout is the definitive guide.

## Multi-column & detection
- Two-column papers: a central gutter (no text) splits the page. Process each
  column independently; column-2 formulas may center relative to the column, not
  the page.
- Centering alone is not sufficient. Combine signals: vertical whitespace above/
  below, no prose words on the line, presence of math symbols/operators, optional
  right-margin equation number. Review ambiguous lines against the rendered page —
  avoid both omissions and extra non-formula lines.

## Rendering equivalence (ground truth)
- Two LaTeX strings are equivalent iff they render identically.
- `\frac{a}{b}` == `\dfrac{a}{b}`; `\sum_{i=1}^{N}` == `\sum_{i=1}^N`.
- `a+b` != `b+a` (different output). Do not reorder/rename/simplify.
- You need not recover the exact source — only output that renders like the PDF.

## Cleaning (handled by scripts/process.py)
- Remove `\tag{...}` / `\tag*{...}` and trailing numbering like `\quad (3)`,
  `\qquad(1)`, or a bare trailing `(1)`.
- Strip trailing sentence punctuation (comma/period) that belongs to the prose.
- Collapse internal whitespace to single spaces (math-mode-safe).
- Never alter mathematical content.

## Deduplication
- No duplicate lines; a formula restated on several pages appears once.
- Distinct formulas that merely look similar (same structure, different variables)
  are separate entries and all kept.

## Correctable errors (append a fixed line; keep the original)
1. Mismatched `\left`/`\right` delimiters. All delimiter types must be checked,
   including angle brackets `\langle`/`\rangle` (multi-character — easy to miss),
   `|`, `\|`, `\lvert`/`\rvert`, `\lVert`/`\rVert`, `()`, `[]`, `\{\}`, `<>`, and
   the invisible `.`. No universal rule says which side to change — infer the
   intended pair from repeated notation, the group's mathematical role, and the
   visible glyphs; supply it as a manual correction when the auto default is wrong.
   When replacing, process from the end of the string backward to keep indices valid.
2. Misspelled LaTeX commands (`\alhpa`→`\alpha`, `\sinn`→`\sin`) — only when the
   rendered symbol clearly supports it. Legitimate custom macros are not errors.
3. Missing grouping braces (`x_ij`→`x_{ij}`) that change rendering.

## Non-correctable (leave as-is)
- Wrong physics/math (sign errors, etc.) that are visually intentional.
- Stylistic choices (`\cdot` vs `\times`, `\hbar` vs `h`, variable names).
- Display preferences (`\frac` vs `\dfrac`, `\displaystyle`, delimiter sizing).

## Output format
```
$$original_1$$
$$original_2$$
...

$$fixed_1$$
$$fixed_2$$
```
- Originals first (one per line, deduped), a blank line, then appended corrections.
- Corrections are additions, NEVER replacements — both versions remain in the file.
- If no corrections are warranted, only the originals section is written.
