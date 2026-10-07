---
name: display-latex-formula-extraction
description: Extract display-mode mathematical formulas from a PDF into a deduplicated Markdown file of one $$...$$ formula per line. Use when formulas must visually reproduce a research paper, equation-number and trailing-punctuation artifacts must be removed, and only clearly supported syntax/typographic corrections may be appended after the originals.
---

# Display LaTeX Formula Extraction

## Scope and output contract

Extract only mathematics that occupies its own display line. Do **not** extract inline math sharing a line with prose. Process every page, including both columns independently on multi-column pages.

Write the final file to `/root/latex_formula_extraction.md` (unless a different explicit output path is supplied). It must contain:

- exactly one `$$formula$$` entry per nonempty line;
- original formulas first, in document reading order;
- warranted corrected versions only after every original formula;
- no duplicate formula contents and no blank lines;
- no equation tags/numbers or trailing sentence commas/periods.

A correction is an *additional* formula, never a replacement for the extracted original. Do not correct scientific content, variable choices, signs, notation preferences, or merely unfamiliar macros.

## Required review workflow

1. **Inspect the PDF visually, page by page.** Render pages at sufficient resolution and inspect the page image alongside extracted text. PDF text extraction is only a lead: it cannot recover source LaTeX faithfully.
   - If Poppler is available, `pdftotext -layout` is useful for finding likely equations and `pdftoppm -png -r 200` is useful for visual review.
   - For two-column pages, inspect the left and right column as separate layout regions. Do not reject a second-column formula because it is not centered on the whole page.
2. **Select display candidates using multiple signals.** Look for a line/region separated by vertical whitespace, no prose on the same baseline, mathematical glyphs/operators/structured scripts, and optionally a right-margin equation number. Centering alone is not enough; left-aligned displays are valid.
3. **Transcribe each selected formula into LaTeX.** Preserve symbol order, scripts, fractions, roots, accents, delimiters, matrices, spacing where visually meaningful, and line structure. Equivalent LaTeX source is acceptable only if its display rendering matches the PDF. Do not use equation numbers as formula content.
4. **Visually validate the transcription.** Render candidate LaTeX with an available local TeX/MathJax renderer and compare it against the PDF crop. Resolve ambiguous OCR glyphs from the page image, especially `l`/`1`, Greek letters, minus signs, and sub/superscript attachment.
5. **Clean only extraction artifacts.** Remove terminal `\tag{...}`/`\tag*{...}`, a terminal number preceded by layout spacing such as `\quad (3)`, and a final literal comma or period. Collapse incidental whitespace. Do not simplify or algebraically reorder content.
6. **Check for real typographic/syntax defects.** In particular inspect every `\left`/`\right` pair. Supported paired delimiters include `()`, `[]`, `\{\}`, `\langle`/`\rangle`, `|`, and `\|`; `.` is an invisible one-sided delimiter. A mismatch must be confirmed against the visible formula and surrounding repeated notation before adding a corrected version. Do not automatically assume whether the left or right delimiter was intended. Similarly, correct a misspelled standard command only when the printed glyph/context clearly establishes it; legitimate custom macros are not typos.
7. **Build and validate the final file** using `scripts/build_formula_file.py`. Supply formulas only after the human/visual review; the helper deliberately does not invent LaTeX from PDF glyphs or silently correct formulas.

## Builder interface

`scripts/build_formula_file.py` reads one JSON object from stdin and emits one JSON report to stdout.

Input schema:

```json
{
  "originals": ["x=y", {"formula": "\\frac{a}{b}", "page": 2}],
  "corrections": ["\\left\\{x\\right\\}"],
  "output_path": "/root/latex_formula_extraction.md"
}
```

`originals` and `corrections` are ordered arrays. An item may be a formula string or an object with a required `formula` string; metadata such as `page` is ignored. Formula strings may be supplied with or without outer `$$`. `output_path` defaults to `/root/latex_formula_extraction.md`.

The helper removes defined terminal artifacts, deduplicates by the cleaned inner formula while preserving first occurrence and section ordering, writes UTF-8 output, reports dropped duplicates, and reports suspicious `\left`/`\right` mismatches. Its mismatch report is a review prompt, not evidence to alter a formula automatically. A nonempty `corrections` input must have been justified by visual/contextual review.

Example runnable call (values are illustrative only and not paper content):

```bash
python3 scripts/build_formula_file.py <<'JSON'
{"originals":["\\frac{a}{b}\\quad (1)"],"corrections":[],"output_path":"/root/latex_formula_extraction.md"}
JSON
```

The returned report should show the intended output path, `valid_file: true`, and no unexpected duplicate removals. Review `delimiter_issues` manually; known erroneous originals may legitimately appear there because originals must be retained. Finally inspect the actual Markdown file: every line must begin and end with `$$`, contain no blank lines, and corrected entries (if any) must follow all originals.
