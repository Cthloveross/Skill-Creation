---
name: interactive-pdf-court-form-filler
description: Inspect, populate, and verify an interactive court PDF (AcroForm) from a supplied case description. Use for SC-100 and similar forms when a blank PDF and a required filled-PDF path are provided.
---

# Interactive PDF Court Form Filler

Use this Skill to create a filled copy of a supplied interactive PDF without altering court-only, optional, or unmentioned fields. Field names, types, and available button states are properties of the supplied PDF, so inspect them at runtime rather than assuming a template revision.

## Prerequisites and limits

* The source must be an interactive AcroForm PDF. `scripts/inspect_pdf.py` reports a clear error when no AcroForm is present or when the document contains XFA data that this Skill cannot safely populate.
* The scripts use `pypdf`, which must be available in the execution runtime.
* Do not sign the form, invent dates, case numbers, hearing details, fees, service details, attorney information, additional parties, or any fact absent from the case description.
* Preserve the exact requested date format. Convert a natural-language date to `YYYY-MM-DD` only when the request explicitly requires that format.

## Procedure

1. Read the task request and make a fact sheet containing only stated facts: plaintiff(s), defendant(s), contact and address components, amount, concise claim basis, incident date range, filing date, venue facts, and explicitly stated yes/no facts. Distinguish required form answers from optional/court-completed content.
2. Inspect the actual PDF:

   ```sh
   python /app/environment/skills/current/scripts/inspect_pdf.py <<'JSON'
   {"input_pdf":"/root/blank.pdf"}
   JSON
   ```

   The JSON response lists every terminal field with its exact full name, field type (`/Tx`, `/Btn`, `/Ch`, etc.), existing value, and legal button export states. Save this response if it is lengthy. If needed, render or text-extract the supplied PDF with available runtime tools to associate its field names with visible labels. Never select a checkbox export state by guessing: use the reported `states` value.
3. Identify only the fields corresponding to facts in the fact sheet. For an SC-100, ordinarily this includes plaintiff and defendant identity/address/contact fields, the requested amount, the facts supporting the claim, appropriate claim-period dates, required venue basis, and the plaintiff's filing date where present. It does **not** ordinarily include court name/address, case number, clerk/translator/interpreter fields, hearing date/time, signature, service information, attorney details, other optional contact fields, or checkboxes not supported by the stated facts.
4. Build a JSON request for `fill_pdf.py`. Keys in `fields` must be exact names from inspection. Text values are strings. A button value is an exact export state reported by inspection; set it to `"Off"` only when a stated answer requires clearing it. Do not include fields that should remain blank.

   ```sh
   python /app/environment/skills/current/scripts/fill_pdf.py <<'JSON'
   {
     "input_pdf": "/root/blank.pdf",
     "output_pdf": "/root/filled.pdf",
     "fields": {
       "Exact text field name": "value derived from the case description",
       "Exact checkbox/radio field name": "/ExactOnState"
     }
   }
   JSON
   ```

   The command emits a JSON validation report. Treat `ok: false`, a nonempty `missing_fields`, or any `mismatches` as failure: correct the mapping or value and rerun from the original blank PDF. A successful report means the output was reopened and its semantic field values were compared with the requested values.
5. Confirm the requested output path exists and is the filled copy. Keep the original source unchanged. If the task demands a visual review, render the output and check that values appear in their intended locations; field semantics remain the primary validation.

## Script input/output schemas

`inspect_pdf.py` reads `{"input_pdf": "path"}` from stdin and writes:

```json
{"ok": true, "input_pdf": "...", "field_count": 0, "fields": [{"name":"...","type":"/Tx","value":"...","states":[],"options":[]}]}
```

`fill_pdf.py` reads:

```json
{"input_pdf":"path", "output_pdf":"path", "fields":{"exact field name":"string value"}}
```

and writes a report with `ok`, `output_pdf`, `written_fields`, `missing_fields`, `mismatches`, and `observed`. It exits nonzero for malformed input, an unsupported field type/value, failure to write, or failed semantic verification.

The scripts deliberately require explicit field mapping. This prevents accidental completion of optional fields and makes the method applicable to changing court form revisions.
