---
name: pdf-display-latex-extraction
description: Extract every display-mode mathematical formula from a PDF into a one-line-per-formula Markdown file. Use this for research-paper PDFs when formulas must match the visual page, equation tags and terminal prose punctuation must be removed, duplicates excluded, and justified syntax-only corrected variants appended after originals.
---

# PDF display-LaTeX extraction

## Scope and output

Use this Skill for PDF source recovery, where exact original TeX source is unavailable and a rendering-equivalent LaTeX representation must be constructed. The required output is a UTF-8 Markdown file containing only lines of the form `$$...$$`, with no blank lines. It contains:

1. each distinct cleaned display formula in document/page reading order; then
2. each distinct, justified syntax/typographical correction, after every original.

Do not extract inline math. Do not change mathematics, notation, term order, signs, or styling merely because another representation is preferable. Retain the uncorrected original whenever a correction is added.

## Inputs

At runtime, identify the supplied PDF and requested destination. For the standard task they are `/root/latex_paper.pdf` and `/root/latex_formula_extraction.md`.

The included `scripts/assemble_formulas.py` accepts reviewed formula strings and deterministically cleans, validates, de-duplicates, and writes the final file. It does **not** claim to recover LaTeX from PDF glyphs automatically.

## Extraction procedure

1. **Inventory and render every page.** Obtain the page count (for example with `pdfinfo`) and render pages at sufficiently high resolution (roughly 200--300 DPI) for visual inspection. Also obtain layout-preserving text with a PDF text extractor when available. Text extraction is a candidate aid only; never assume its character order is correct for math.
2. **Process each layout region independently.** On multi-column pages, inspect both columns separately and in normal reading order. A formula may be centered relative to a column rather than the whole page.
3. **Select display formulas only.** A candidate should occupy its own visual line/region, normally be separated vertically from prose, and have mathematical glyphs or structure. An equation number at the right margin does not make the number part of the formula. Exclude inline expressions sharing a prose baseline, headings, figure labels, and ordinary centered prose.
4. **Transcribe against the rendered page.** Construct conventional LaTeX that renders like the formula. Preserve fractions, scripts, radicals, accents, operator limits, matrices/cases, arrows, spacing where visually meaningful, and delimiter types. For ambiguous candidates, compare rendered LaTeX with a page crop rather than trusting OCR. A semantically equivalent reordering is not sufficient.
5. **Clean only output artifacts.** Remove a terminal `\\tag{...}` and terminal equation-number artifacts such as `\\quad (3)` / `\\qquad(2.1)`, then remove a terminal comma or period belonging to surrounding prose. Do not remove mathematical internal punctuation. Collapse incidental whitespace.
6. **Review potential typos conservatively.** Check malformed LaTeX, unmistakably misspelled standard commands, missing script grouping when the visible layout establishes it, and mismatched `\\left`/`\\right` delimiters. Delimiter review must include `()`, `[]`, `\\{`/`\\}`, `\\langle`/`\\rangle`, `|`, `\\|`, and the one-sided `.` delimiter, and must handle nested pairs as a stack. For a non-dot mismatch, decide which delimiter to change from the local mathematical role and neighboring delimiters (for example, an inner operand group conventionally uses parentheses inside an outer function argument); append that evidenced repair as a new line. Do not correct scientific/physics mistakes or unfamiliar but potentially defined macros.
7. **Assemble the file.** Put reviewed original candidates and separately reviewed corrected candidates in JSON and invoke the packaged script. Inspect its warnings; resolve suspicious delimiter/brace reports by returning to the page image. The script intentionally does not auto-correct formulas.
8. **Final visual and structural review.** Render each output line in display math if a TeX/MathJax renderer is available. Compare it to its page crop, verify all pages and columns were covered, and verify that tags, numbering, terminal prose punctuation, duplicates, blank lines, and inline formulas are absent.

## Assembly script

Run from the Skill directory, supplying JSON on stdin:

```sh
python3 scripts/assemble_formulas.py <<'JSON'
{
  "output_path": "/root/latex_formula_extraction.md",
  "originals": ["reviewed display formula", "another reviewed formula"],
  "corrections": ["reviewed corrected form"]
}
JSON
```

Input schema:

- `output_path` (string): destination Markdown path.
- `originals` (array of strings): display formulas in document reading order, without or with outer `$$` delimiters.
- `corrections` (array of strings, optional): syntax-only corrected variants in the order corresponding to the review. They are appended after originals.

The script emits a JSON report to stdout with `written`, `originals_written`, `corrections_written`, `warnings`, and `output_path`. It exits nonzero on malformed JSON, non-string formula entries, empty formulas, or an unsafe output path. Warnings identify unmatched braces and suspicious non-dot `\\left`/`\\right` delimiter mismatches; warnings require human/page review rather than automatic changes.

The script removes only prescribed terminal tag/number/punctuation artifacts, wraps each result exactly once in `$$`, and de-duplicates complete cleaned formula content while preserving first occurrence and originals-before-corrections ordering. A correction that cleans to the same content as an existing line is omitted to honor the no-duplicate requirement.

## Completion checklist

- Every PDF page and every column/layout region was inspected.
- Every selected item is a visually separate display formula, not inline prose math.
- Each line visually matches the page formula and is exactly `$$formula$$`.
- Formula content has no terminal tag/equation number or terminal sentence comma/period.
- No output line is duplicated and no blank/non-formula lines remain.
- All originals appear before any corrected variants.
- Corrections are only evidenced rendering/syntax/typo repairs, and each original remains present.
