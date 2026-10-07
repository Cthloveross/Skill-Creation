---
name: safe-docx-offer-letter-filler
description: Fill a DOCX offer-letter template from a JSON employee record, including IF_RELOCATION-style conditional sections, while handling placeholders split across Word runs and preserving the package structure.
---

# Safe DOCX offer-letter filler

Use this Skill when a Word `.docx` template contains `{{FIELD_NAME}}` placeholders and conditional regions such as `{{IF_RELOCATION_PACKAGE}}...{{END_IF_RELOCATION_PACKAGE}}` (including the requested `IF_RELOCATION` form). It operates directly on OOXML text nodes, so markers may be split between Word runs.

## Inputs

The executable reads one JSON object from standard input:

```json
{
  "template": "/root/offer_letter_template.docx",
  "data": "/root/employee_data.json",
  "output": "/root/offer_letter_filled.docx"
}
```

`data` must be a JSON object whose keys match template placeholder names. Values are converted to text. A conditional `IF_KEY` is retained only when `data["KEY"]` is `Yes` (case-insensitive); `true` and `1` are also accepted as affirmative values. Missing placeholder or conditional keys are reported as errors rather than silently left in the document.

## Run

From the Skill directory:

```sh
python3 scripts/fill_offer_letter.py <<'JSON'
{"template":"/root/offer_letter_template.docx","data":"/root/employee_data.json","output":"/root/offer_letter_filled.docx"}
JSON
```

The script emits a JSON result on stdout. On success it creates the requested output DOCX. It processes every `word/*.xml` part, including headers, footers, tables, and text boxes represented by Word text nodes.

## Method and validation

The script reads the DOCX as a ZIP package and changes only Word XML parts containing template text. It treats the concatenated `w:t` text nodes as a logical span, allowing a token divided among runs to be found. Replacement text is inserted in the starting text node, while prefix and suffix text stay in their original nodes to preserve surrounding run formatting and structure.

False conditional regions have their logical text removed; paragraphs wholly contained by the region are removed as well. True regions retain their contents but lose both control markers. Finally, the generated ZIP is reopened, all XML parts are parsed, required DOCX package parts are checked, and all `{{...}}` markers are rejected. A validation failure means the output should not be used.
