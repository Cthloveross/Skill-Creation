---
name: interactive-pdf-form-filler
description: >-
  Inspect, fill, and verify interactive (AcroForm) PDF form fields while
  preserving the original document structure. Use when a task supplies a
  fillable PDF (e.g. a California Small Claims SC-100 form) plus a natural
  language description of the values to enter, and asks for a saved filled
  PDF. The Skill reads the actual field names, types, selectable states, and
  tooltips at runtime from the supplied file, writes only the requested
  semantic values, saves a new PDF, and reopens it to confirm the values
  were stored.
---

# Interactive PDF Form Filler

## When to use
A task gives you a fillable PDF and asks you to fill specific fields derived
from a case/instruction description, then save a filled copy. Nothing about
the concrete field names, party details, or answers is known in advance:
**inspect the supplied file at runtime** and map the description onto the
real fields.

## Method (do this every run)
1. **Inspect** the blank PDF to discover every interactive field, its type
   (`/Tx` text, `/Btn` checkbox/radio, `/Ch` choice), current value, the
   on-state names for buttons, and the human-readable tooltip (`/TU`). The
   tooltip usually explains what the field means (e.g. "Plaintiff's name",
   "Mailing address", a specific checkbox option). Use it to map description
   facts to field names.
2. **Plan the mapping** from the instruction's facts to concrete field names:
   - Fill only the fields the instruction asks for. Leave court-filled,
     clerk-only, optional, or unmentioned fields empty.
   - Honor any requested formatting (e.g. a date format such as
     `xxxx-xx-xx` means ISO `YYYY-MM-DD`). Convert dates like
     "January 19, 2026" to the requested format.
   - For text fields pass the plain string value.
   - For checkbox/radio (`/Btn`) fields pass the **exact on-state string**
     reported by the inspector for that field (for example a value from the
     field's `states` list such as `/Yes` or an option name). Do not guess
     generic values; a wrong state leaves the box unchecked.
   - Split components correctly (name, street, city, state, ZIP, phone,
     email, claim amount, reason, dates, filing-venue selection, etc.) by
     matching tooltips/field names, not by assuming a layout.
3. **Fill** the form with `scripts/fill_form.py`, which clones the input,
   writes the given field values, sets the `NeedAppearances` flag so viewers
   regenerate appearances, and saves to the output path. This preserves the
   existing document structure (it appends the original and only updates the
   named fields).
4. **Verify** with `scripts/verify_fields.py`, which reopens the saved PDF
   and reports the stored value for each field you intended to set. Confirm
   every requested field holds the expected value (checkboxes show the
   on-state, not the off/empty state) before considering the task done.

If a requested value has no matching field, record that it is unsupported
rather than forcing it into an unrelated field.

## Scripts
All scripts read a JSON object from stdin and print a JSON object to stdout.
They use `pypdf` (fallback import `PyPDF2`). Install if missing:
`pip install pypdf`.

### scripts/inspect_fields.py
Input: `{"pdf_path": "/root/sc100-blank.pdf"}`
Output: `{"count": N, "fields": [{"name":..., "type":..., "value":...,
"states": [...], "tooltip":...}, ...]}`.
`states` lists valid on-state names for `/Btn` fields.

Example:
```
echo '{"pdf_path":"/root/sc100-blank.pdf"}' | python3 scripts/inspect_fields.py
```

### scripts/fill_form.py
Input:
```
{"input_pdf": "/root/sc100-blank.pdf",
 "output_pdf": "/root/sc100-filled.pdf",
 "fields": {"<field name>": "<value>", "<checkbox name>": "/Yes"}}
```
Output: `{"ok": true, "written": [names...], "missing": [names not found],
 "output_pdf": "..."}`. Fields present in the mapping but absent from the
PDF are reported under `missing` so you can fix the mapping.

Example:
```
cat fields.json | python3 scripts/fill_form.py
```
where `fields.json` is the full input object you build at runtime.

### scripts/verify_fields.py
Input: `{"pdf_path": "/root/sc100-filled.pdf", "expect": {"<name>":
"<value>"}}` (`expect` optional).
Output: `{"fields": {name: stored_value}, "checks": [{"name":..,
"expected":.., "actual":.., "match": bool}]}` so you can assert every
intended value was written.

## Validation checklist (run before finishing)
- Inspect output lists the fields you plan to use; tooltips confirm meaning.
- `fill_form.py` returns `ok:true` with an **empty** `missing` list for the
  fields you set.
- `verify_fields.py` shows each requested field equal to the intended value
  (dates in the requested format; checkboxes showing their on-state).
- Fields not mentioned in the instruction remain empty in the output.
