---
name: latex-display-formula-extraction
description: >-
  Extract display-mode (own-line) LaTeX formulas from a research-paper PDF,
  clean them (strip equation tags/numbers and trailing punctuation, normalize
  whitespace), deduplicate, detect syntax/typo errors (mismatched \left/\right
  delimiters, misspelled LaTeX commands), and write a markdown file with all
  original formulas first followed by appended corrected versions, one formula
  per line wrapped in $$...$$. Use when a task asks to extract "formulas in
  their own line" from a PDF into a .md file in that two-section format.
---

# LaTeX Display-Formula Extraction

## When to use

Use this Skill for tasks that supply a research-paper PDF and ask you to:

1. Identify every **display-mode** formula (one that occupies its own line,
   centered or left-aligned within its column, visually separated from prose).
   Ignore inline formulas embedded inside sentences.
2. Transcribe each as raw LaTeX inside `$$ ... $$` that renders the same as the PDF.
3. Clean the formulas (remove `\tag{...}`, trailing equation numbers like
   `\quad (1)`, and trailing commas/periods; collapse whitespace).
4. Deduplicate (a formula restated on several pages appears once).
5. Detect only **syntactic/typographic** problems (mismatched brackets,
   misspelled commands, missing grouping braces) and append corrected copies
   AFTER all originals. Never replace an original with its fix; keep both.
6. Write everything to the requested output file (default
   `/root/latex_formula_extraction.md`) with one formula per line.

Read the current task's `opening` for the exact PDF path and output path; do not
hardcode them. The output path for this task family is
`/root/latex_formula_extraction.md` unless the task says otherwise.

## Important: what counts as an error

Correctable (fix and append): mismatched `\left`/`\right` delimiters
(`\left\{ ... \right]`), misspelled LaTeX commands (`\alhpa` -> `\alpha`,
`\sinn` -> `\sin`), missing grouping braces that change rendering (`x_ij` ->
`x_{ij}`). Confirm against the rendered page; papers may define legitimate
custom macros.

Do NOT touch: wrong physics/math (a `+` that should be `-`), stylistic choices
(`\cdot` vs `\times`, `\frac` vs `\dfrac`, delimiter sizing, `\displaystyle`).
Two strings are equivalent when they render identically; you need rendering
equivalence, not the exact original source.

## Recommended workflow

Formula recognition from a PDF is lossy and generally needs visual reading, so
the reusable scripts handle the deterministic parts (rendering help, text dump,
cleaning, bracket validation, typo flagging, dedup, file assembly) while you
supply/confirm the transcribed LaTeX.

1. **Inspect the PDF.** Render pages to images and dump text to locate
   display-mode lines on each page:
   `python3 scripts/pdf_render.py <<<'{"pdf":"/root/latex_paper.pdf","out_dir":"/root/pages","dpi":200}'`
   `python3 scripts/pdf_text.py  <<<'{"pdf":"/root/latex_paper.pdf"}'`
   Use the images to decide which lines are display-mode (own line, no prose on
   the line, vertical whitespace above/below, possibly an equation number at the
   right margin). Handle two-column layouts by treating each column separately.
2. **Transcribe** each display-mode formula to LaTeX that renders like the PDF.
   Keep raw strings (no `$$`). If internet is available and a tool is installed,
   you may render candidate LaTeX (e.g. via MathJax/matplotlib) to confirm.
3. **Validate brackets and flag typos** on the transcribed list:
   `python3 scripts/validate_brackets.py <<<'{"formulas":["...","..."]}'`
   `python3 scripts/detect_typos.py     <<<'{"formulas":["...","..."]}'`
   These report candidates only; you decide the fix using the PDF and
   surrounding notation (the correct side of a bracket mismatch is
   context-dependent).
4. **Assemble the output file**. Pass the raw originals and the fixed copies you
   decided on; the script cleans originals, deduplicates them, writes them
   first, then a blank line, then the corrected copies, one per line in
   `$$...$$`:
   `python3 scripts/assemble.py <<<'{"formulas":[...originals raw...],"corrected":[...fixed raw...],"output_path":"/root/latex_formula_extraction.md"}'`
5. **Verify** by reading the output file and re-running assemble to confirm it
   regenerates the same content. Check: no duplicate original lines, every line
   is `$$...$$`, corrected lines come only after originals, and no cleaning
   artifact (stray `\tag`, trailing `,`/`.`, equation number) remains.

If a required capability is unavailable (e.g. no PDF/render library and no
network), report the limitation explicitly rather than inventing formulas.

## Script I/O contract

All scripts read one JSON object from stdin and print one JSON object to stdout.

- `pdf_render.py`  in `{pdf, out_dir, dpi?}` -> `{pages:[paths], engine}`.
- `pdf_text.py`    in `{pdf}` -> `{pages:[{page, text}], engine}`.
- `clean_formula.py` in `{formulas:[str]}` -> `{cleaned:[str]}`.
- `validate_brackets.py` in `{formulas:[str]}` ->
  `{results:[{index, formula, mismatches:[{open, close, open_pos, close_pos,
  fix_match_close, fix_match_open}], ok}]}`.
- `detect_typos.py` in `{formulas:[str]}` ->
  `{results:[{index, formula, unknown:[{command, pos, suggestion}]}]}`.
- `assemble.py` in `{formulas:[str], corrected?:[str], output_path:str,
  clean_corrected?:bool}` -> `{written, output_path, n_originals,
  n_corrected, bracket_report}` and writes the markdown file.

`fix_match_close` is the formula rewritten so the closing delimiter matches the
opening; `fix_match_open` matches the opening to the closing. Pick the one the
PDF supports.

See `references/method.md` for details on cleaning rules, delimiter groups
(including angle brackets `\langle`/`\rangle`, `|`, `\|`, and the invisible `.`),
and output layout.
