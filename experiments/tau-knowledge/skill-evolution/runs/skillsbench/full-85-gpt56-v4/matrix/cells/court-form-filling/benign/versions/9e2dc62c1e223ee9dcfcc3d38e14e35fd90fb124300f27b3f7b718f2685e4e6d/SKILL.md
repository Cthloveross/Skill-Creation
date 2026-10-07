---
name: interactive-pdf-court-form-filler
description: Inspect, populate, and verify AcroForm or hybrid XFA court PDFs from a supplied case description. Use when a blank interactive PDF and a required filled-PDF output path are provided, including California SC-100 revisions.
---

# Interactive PDF Court Form Filler

Create a filled copy of the supplied interactive PDF while leaving court-completed, optional, and unmentioned fields blank. Never assume field names, checkbox values, or a particular SC-100 revision: inspect the actual document first.

## Boundaries

* Use only facts stated in the request. Do not invent a court name, case number, hearing details, fees, service information, attorney details, other parties, or a signature. A stated filing/declaration date may be entered in its date field, but do not sign for the user.
* Preserve an explicitly required date format. Convert natural-language dates to `YYYY-MM-DD` only if the request requires it.
* The scripts require Python 3 and `pypdf`. They support ordinary AcroForms and hybrid PDFs carrying an XFA `datasets` packet. They reject noninteractive PDFs, malformed XFA datasets, unknown fields, and unsupported button states rather than guessing.

## Workflow

1. Make a fact sheet from the request: party names and contact/address components, amount, concise reason and calculation, incident date or period, filing date, venue basis and zip, and only yes/no facts actually stated or necessarily established by the described party/amount. Separate court-only and optional blanks.
2. Inventory the real form:

   ```sh
   python3 /app/environment/skills/current/scripts/inspect_pdf.py <<'JSON'
   {"input_pdf":"/root/blank.pdf"}
   JSON
   ```

   For an AcroForm, use `fields`: exact `name`, `type`, accessible `label`, and legal button `states`. For `form_kind: "hybrid-xfa"`, also use:
   * `xfa_data_fields`: editable XFA data-leaf `path` values and their current values;
   * `xfa_template_fields`: visible template paths, captions, UI types, check/radio `item_values`, and same-name candidate XFA data paths.

   Match labels/captions to the fact sheet. For an XFA field, copy the exact data-leaf path from `xfa_data_fields`; template paths are evidence for mapping, not fill keys. Do not infer an XFA checkbox value: use the template's advertised `item_values` for the matching caption.
3. Fill only the selected fields from the original blank PDF:

   ```sh
   python3 /app/environment/skills/current/scripts/fill_pdf.py <<'JSON'
   {
     "input_pdf":"/root/blank.pdf",
     "output_pdf":"/root/filled.pdf",
     "fields": {
       "exact AcroForm field name": "derived text or reported button state"
     },
     "xfa_fields": {
       "exact/path/from/xfa_data_fields": "derived value"
     }
   }
   JSON
   ```

   `fields` and `xfa_fields` are independently optional; use `fields` for ordinary AcroForm fields and `xfa_fields` for a hybrid XFA form. On a hybrid form, filling its XFA data is necessary because many XFA widgets have no usable AcroForm appearances. Do not include keys for blanks. Text/choice values are strings. An AcroForm button value must be exactly one reported state (including its leading `/` if reported); an XFA checkbox/radio value must be an advertised XFA item value.
4. Require a successful JSON report: `ok: true`, no `missing_fields`, and no `mismatches`. The script reopens the saved PDF and compares requested AcroForm `/V` values and XFA dataset values semantically. For an XFA text value whose AcroForm counterpart is structurally unambiguous, it also mirrors the value into that counterpart for compatibility with generic PDF readers; `mirrored_xfa_fields` reports these supplemental values. Confirm the requested output path exists and the original remains unchanged. If the runtime has a compatible renderer and visual review is required, render the output as an additional check; do not replace semantic validation with a screenshot.

For SC-100, normally fill party identity/contact/address, claim amount, factual basis, relevant period, amount calculation, request-made answer if stated, venue basis/zip, and stated filing date. Leave court header/case number/order, mailing addresses marked “if different,” attachments, and signature blank unless the request specifically supplies and requires them.

## JSON interfaces

`inspect_pdf.py` reads `{"input_pdf":"path"}` on stdin and emits JSON with `ok`, `form_kind`, `field_count`, and `fields`; hybrid XFA forms additionally include `xfa_data_fields` and `xfa_template_fields`.

`fill_pdf.py` reads `{"input_pdf":"path","output_pdf":"path","fields":{},"xfa_fields":{}}` on stdin and emits `ok`, `output_pdf`, `written_fields`, `written_xfa_fields`, `mirrored_xfa_fields`, `missing_fields`, `mismatches`, and `observed`. It exits nonzero on invalid input or failed verification.
