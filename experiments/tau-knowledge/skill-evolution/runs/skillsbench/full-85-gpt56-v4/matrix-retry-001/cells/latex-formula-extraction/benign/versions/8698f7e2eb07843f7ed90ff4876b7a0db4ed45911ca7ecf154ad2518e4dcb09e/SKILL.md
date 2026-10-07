---
name: pdf-display-latex-extraction
description: Extract display-mode mathematics from a research-paper PDF into a one-line-per-formula Markdown file, with cleaned equation-number artifacts, deduplication, and separately appended, human-verified syntax corrections. Use when visual PDF layout—not inline text—is the source of truth.
---

# PDF display-math extraction

This Skill produces the requested `$$...$$` lines from a supplied PDF. It deliberately treats PDF recovery as visual transcription: a PDF normally does not retain its original LaTeX source, so text extraction is evidence only. Do not infer or alter mathematical meaning.

## Inputs and output

* Read the PDF path supplied by the task (for this task, `/root/latex_paper.pdf`).
* Create the task-requested output file (for this task, `/root/latex_formula_extraction.md`).
* The output contains no prose, headings, blank lines, or code fences: exactly one `$$formula$$` per line.
* Use `scripts/build_formula_output.py` after review to clean, deduplicate, validate, and write the final lines.

The builder reads one JSON object from stdin:

```json
{
  "originals": [{"formula": "x = y", "page": 3}],
  "corrections": [{"formula": "x = y", "source": "optional explanation"}],
  "output_path": "/root/latex_formula_extraction.md"
}
```

`page` and `source` are optional audit metadata and are never written to the Markdown. `formula` may be bare LaTeX or be wrapped in `$$...$$`. The script emits a JSON report on stdout. It does not execute any banking or other external action.

## Extraction procedure

1. Inspect page count and obtain an initial layout-oriented text index. Typical available Poppler commands are:
   ```sh
   pdfinfo /root/latex_paper.pdf
   pdftotext -layout /root/latex_paper.pdf /tmp/paper-layout.txt
   pdftoppm -r 200 -png /root/latex_paper.pdf /tmp/page
   ```
   If one is unavailable, use another installed PDF viewer/text extractor; do not assume its text stream is LaTeX.
2. Inspect every rendered page, including both columns in multi-column pages. Record only math that occupies its own layout line/region. A formula may be centered or left-aligned within a column; use separation from prose, math glyphs, and vertical whitespace rather than centering alone. Exclude inline expressions, table entries, figure labels, and equation numbers.
3. Transcribe each display formula to LaTeX that renders like the visible formula. Preserve order of first occurrence. Use layout text to help with characters and long expressions, but compare doubtful subscripts, superscripts, fractions, roots, delimiters, accents, matrices, and operator names against the page image. Do not manufacture LaTeX commands from an unreliable extraction.
4. Put all initially transcribed formulas in `originals`. Retain originals even if a real rendering/syntax typo is found. The builder removes terminal `\tag{...}` and conventional terminal equation-number fragments such as `\quad (12)` / `\qquad(2.3)`, collapses whitespace, and removes a final literal comma or period.
5. Run the builder, then examine the returned `delimiter_issues`. It checks `\left`/`\right` pairs, including `\langle`/`\rangle`, `|`, `\|`, braces, brackets, parentheses, and one-sided `.` delimiters. A reported mismatch is a review prompt, not permission for automatic modification.
6. Add a `corrections` entry only when the PDF/context clearly establishes a typographical or LaTeX-syntax correction (for example, a mismatched delimiter, unmistakably misspelled standard command, or broken grouping). Never correct signs, physics, variable choices, ordering, or stylistic source choices. Corrections are appended only after every deduplicated original and never replace one.
7. Review the generated file: each nonempty line must start and end with `$$`, have no embedded newline, and represent only display formula content. Render uncertain final LaTeX with an available TeX/MathJax renderer when possible and compare it to the PDF image. The builder's JSON report must show `ok: true`; resolve any `delimiter_issues` before deciding whether a correction is warranted.

## Runnable call

Write reviewed candidates to a JSON file, then invoke:

```sh
python3 /app/environment/skills/current/scripts/build_formula_output.py \
  < /tmp/formulas.json
```

The `output_path` must be an explicit writable path. The script rejects missing/non-list candidate sections and formulas containing internal `$$`; it writes atomically only after all input formulas have been normalized and checked. Its report lists counts, duplicate suppression, and possible delimiter defects so the executor can make a visual decision.
