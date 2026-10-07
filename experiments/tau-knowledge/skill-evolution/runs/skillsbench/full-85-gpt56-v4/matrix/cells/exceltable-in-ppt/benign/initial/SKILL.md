---
name: update-embedded-currency-rate-pptx
description: Updates one explicitly announced currency-pair rate in an embedded XLSX workbook inside a PowerPoint file, using nearby slide text as the update instruction. Use for PPTX financial-reporting files containing an OOXML embedded Excel currency matrix; it preserves formulas and all non-embedded PPTX parts.
---

# Update an embedded currency-rate workbook in a PPTX

Use `scripts/update_embedded_rate.py` when a presentation has an embedded `.xlsx` rate table and slide text announces an updated rate for a pair such as `USD/EUR` or `USD to EUR`.

The script inspects the supplied presentation at runtime. It does not assume slide numbers, relationship IDs, workbook paths, sheet names, or matrix coordinates. It:

1. follows slide OOXML relationships to discover embedded XLSX parts;
2. reads slide text and ranks text boxes near the OLE workbook object;
3. extracts one pair and one numeric rate from update-like text;
4. locates the pair by matching both the row and column header in the workbook;
5. refuses to overwrite a formula cell;
6. replaces only the embedded XLSX ZIP member, leaving every other PPTX member byte-for-byte unchanged; and
7. reopens the resulting PPTX and workbook and verifies the changed numeric cell and preservation of all formula expressions.

## Run

The program receives one JSON object on standard input and emits one JSON report on standard output.

```sh
python3 /app/environment/skills/current/scripts/update_embedded_rate.py <<'JSON'
{"input_pptx":"/root/input.pptx","output_pptx":"/root/results.pptx"}
JSON
```

Input schema:

- `input_pptx` (required): source `.pptx` path.
- `output_pptx` (required): destination `.pptx` path. It must not be the source path.
- `text_override` (optional): an exact update instruction to use instead of slide text, useful only if the user has provided unambiguous instruction text outside the slide.
- `dry_run` (optional boolean): discover and validate the proposed update without writing the destination.

Success output includes the embedded member path, worksheet, cell, old and new values, selected text, parsed pair, and validation facts. The executor should treat `ok: false` as a stop condition, inspect `error`, and request clarification or use a more appropriate tool rather than guessing.

## Assumptions and failure handling

The supported embedded object is a real `.xlsx` package referenced by a slide relationship, and the table has identifiable row and column currency headers. Currency codes are matched case-insensitively after whitespace normalization. The visible update must contain a conventional three-letter pair and numeric rate. The script deliberately fails on no/multiple update candidates, no/multiple matrix matches, missing workbook, nonnumeric target, or a formula target. This is safer than silently altering a reciprocal, a total, or a calculated rate.

The output preserves formulas as formulas, but `openpyxl` does not calculate formula caches. Thus validation establishes formula-text preservation and workbook/package readability, not recalculated displayed values. If the presentation also has an independently cached chart/table display, do not claim that it was updated unless a compatible Office renderer has refreshed it.

After a successful run, retain the JSON report with the deliverable and confirm that `/root/results.pptx` exists. Do not rebuild slides, layouts, themes, or relationships with a presentation library: this task only replaces the discovered embedded workbook member.
