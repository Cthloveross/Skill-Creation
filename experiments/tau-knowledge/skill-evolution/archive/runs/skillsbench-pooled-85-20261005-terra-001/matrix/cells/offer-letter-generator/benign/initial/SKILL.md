---
name: safe-ooxml-offer-letter-filler
description: Fill a DOCX offer-letter template from a JSON object, including run-split placeholders and the RELOCATION_PACKAGE conditional section. Use when a Word template must retain its existing layout, styles, headers, footers, tables, text boxes, and unrelated package content.
---

# Safe OOXML offer-letter filling

Use `scripts/fill_offer_docx.py` to produce the requested DOCX. The helper uses only Python's standard library. It edits text logically across adjacent Word text (`w:t`) nodes, so a placeholder can be split over multiple runs while the surrounding XML structure remains intact.

## Runtime input

The script receives one JSON object on stdin:

```json
{
  "template_path": "/root/offer_letter_template.docx",
  "data_path": "/root/employee_data.json",
  "output_path": "/root/offer_letter_filled.docx"
}
```

- `template_path` must identify an existing DOCX/OOXML ZIP package.
- `data_path` must identify a UTF-8 JSON file whose root is an object. Its scalar keys are available as placeholders: a key `POSITION` supplies `{{POSITION}}`. JSON `null` becomes an empty string. Arrays and objects are rejected because their intended document representation is ambiguous.
- `output_path` is the DOCX to create. Parent directories must already exist.
- Instead of `data_path`, callers may supply a `values` JSON object directly. If both are supplied, `values` takes precedence.

For the offer-letter task, use the supplied `/root/offer_letter_template.docx` and `/root/employee_data.json` and set `output_path` to `/root/offer_letter_filled.docx`.

Example:

```sh
python3 scripts/fill_offer_docx.py <<'JSON'
{"template_path":"/root/offer_letter_template.docx","data_path":"/root/employee_data.json","output_path":"/root/offer_letter_filled.docx"}
JSON
```

## Method and behavior

1. The helper copies every ZIP member from the input package and only serializes XML parts that actually contain a substitution or relocation control marker. Relationships, media, styles, and untouched XML parts are copied unchanged.
2. It examines all `word/*.xml` parts, covering the main document, headers, footers, table content, text boxes, notes, comments, and glossary content when those use standard Word text nodes.
3. `{{IF_RELOCATION}}...{{END_IF_RELOCATION}}` is evaluated structurally within each part. It retains the inner content only when `RELOCATION_PACKAGE`, after trimming and case-folding, equals `yes`; otherwise it removes the entire conditional region. In either case both control markers are removed. Unbalanced controls fail rather than silently producing a malformed letter.
4. It replaces all uppercase underscore-style placeholders (`{{NAME}}`) using the data object. Missing keys fail. Replacement text is placed at the original placeholder start while text outside the placeholder stays assigned to its existing text nodes, preserving the nearby run/paragraph structure.
5. It writes to a temporary file and atomically replaces the requested output only after validation succeeds.

On success stdout is JSON such as:

```json
{"ok": true, "output_path": "/root/offer_letter_filled.docx", "changed_parts": ["word/document.xml"], "replacements": 8, "relocation_kept": true}
```

The executor must treat a nonzero exit code or an `ok: false` response as failure. Correct the input/template issue rather than delivering that output.

## Validation performed

After writing, the helper reopens the produced ZIP, checks ZIP integrity, requires `[Content_Types].xml` and `word/document.xml`, parses every XML part, and scans the logical Word text of every `word/*.xml` part for any remaining `{{...}}` marker. Thus it detects unresolved placeholders and conditional controls even when they were split over runs. This is a package-level normal-open check using the available standard-library runtime; it does not rebuild the document or require an office application.

If a template contains placeholders in nonstandard XML text locations rather than Word `w:t` text nodes, or requires richer conditional syntax, that is unsupported and should be reported rather than guessed at.
