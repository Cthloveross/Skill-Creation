---
name: pptx-dangling-title-formatter
description: >-
  Detect "dangling" paper-title text boxes in a PowerPoint (.pptx) deck and
  normalize them: set font to Arial 16pt color #989596 non-bold, widen each box
  so its title fits on one line, move each title to the bottom-center of its
  slide, and append a final "Reference" slide listing every unique paper title
  as auto-numbered bullets. Use when a request asks to reformat/relocate loose
  paper titles in a slide deck and build a reference list. Works on any deck via
  python-pptx by inferring roles, fit and placement from the actual package
  geometry and text (never from fixed slide numbers, ids, coordinates or
  hardcoded content strings).
---

# PowerPoint dangling-title formatter

## What this does

Given an input `.pptx`, this Skill:

1. Opens the deck as an OOXML package (python-pptx) and walks every slide and
   every text-bearing shape.
2. Detects **dangling paper titles** as *loose* text boxes: text-bearing
   shapes that are **not placeholders**. A paper-title box dropped on top of a
   slide is an ordinary text box, which distinguishes it from the slide's
   title placeholder (short heading) and from the abstract/body content
   placeholder. This follows the background guidance to infer a fragment's
   *role* from the surrounding slide content rather than fixed slide/shape
   identities, coordinates, or content strings. (Overflow/geometry and
   plain-textbox heuristics remain available as fallbacks, see Tuning.)
3. For every detected title shape:
   - sets font **Arial**, size **16pt**, color **#989596**, **bold=False** on
     all runs (explicitly, because appearance can otherwise be inherited from
     themes/masters/layouts);
   - disables word-wrap and **widens the box so the title is on one line**;
   - repositions the box to the **bottom center** of its slide (document
     units, computed from `slide_width`/`slide_height`).
4. Appends a new final slide titled **"Reference"** whose body lists **every
   unique** detected title (whitespace-normalized, duplicates removed,
   first-occurrence order) as **auto-numbered** bullets (`a:buAutoNum`).
5. Saves to the requested output path and re-opens it to validate.

For the current task the defaults are input `/root/Awesome-Agent-Papers.pptx`
and output `/root/Awesome-Agent-Papers_processed.pptx`, but both are read from
the task request / script input at runtime, not hardcoded into logic.

## Requirements

- Python 3 with `python-pptx`. Install if missing:
  `pip install python-pptx` (internet is allowed in this environment).

## Recommended workflow (executor)

1. **Install dep & inspect first.** Always look at the real deck before
   trusting detection.
   ```bash
   pip install -q python-pptx
   echo '{"pptx":"/root/Awesome-Agent-Papers.pptx"}' \
     | python3 /app/environment/skills/current/scripts/inspect_pptx.py | head -c 4000
   ```
   The output is JSON: per slide a list of shapes with `shape_id`, `name`,
   `left/top/width/height` (EMU), `text`, `is_placeholder`, `ph_type`,
   `eff_font_pt`, `est_text_width_emu`, `is_placeholder` and `overflow`.
   In the default `dangling` mode the detected titles are exactly the shapes
   with `is_placeholder:false` carrying real text (the loose paper-title
   boxes). Confirm those are the paper titles; if detection looks wrong you can
   switch `detect_mode` or tune `width_factor` in the process call.

2. **Process.**
   ```bash
   echo '{"input_pptx":"/root/Awesome-Agent-Papers.pptx",
          "output_pptx":"/root/Awesome-Agent-Papers_processed.pptx"}' \
     | python3 /app/environment/skills/current/scripts/process.py
   ```
   stdout is a JSON summary: `detected_titles`, `unique_titles`,
   `formatted_shapes`, `reference_slide_added`, and a `validation` block.

3. **Verify.** Re-run `inspect_pptx.py` on the output and confirm:
   - every formerly-overflowing title now reports `overflow:false`
     (one line) and Arial/16/non-bold runs;
   - a final slide titled "Reference" exists with one numbered bullet per
     unique title and no duplicates.

## Tuning / fallbacks (process.py JSON input keys)

- `input_pptx`, `output_pptx` (strings) — default to the task paths.
- `width_factor` (float, default `0.52`) — average glyph advance as a fraction
  of the font size (em) used to estimate single-line text width for Arial.
  Increase if a title still wraps; decrease if boxes are far too wide.
- `detect_mode` (string): `"dangling"` (default) treats every
  **non-placeholder** text shape with meaningful text as a dangling paper
  title (the loose text boxes layered on each slide). `"overflow"` instead
  flags only shapes whose text does not fit on one line; `"textboxes"` treats
  every non-title, non-decorative text shape (including content placeholders)
  as a title. Use the alternatives only if inspection shows the default
  mis-selects for a particular deck.
- `min_title_chars` (int, default `8`) — ignore very short labels when
  selecting titles.
- `bottom_margin_in` (float, default `0.2`) — gap from slide bottom edge.
- `number_format` (string, default `arabicPeriod`) — `a:buAutoNum` type for the
  reference list.

If the input file is missing, or `python-pptx` cannot open it, scripts emit
`{"error": "..."}` on stdout and exit non-zero so the failure is observable.

## Notes on correctness

- Font properties are set on individual runs; if a paragraph carries text but
  no explicit runs the script adds one so the formatting is actually stored.
- Widening uses document units (EMU). Width is clamped to the slide width;
  `word_wrap=False` guarantees a single line even when a title is extremely
  long and the box reaches the slide edge.
- The reference slide reuses an existing layout that has both a title and a
  body placeholder when available, else falls back to layout index 1, else a
  blank layout with a manual title+body textbox, so it works across templates.
- Unrelated parts, other shapes, styles and relationships are preserved; the
  deck is edited in place and saved, not rebuilt.
