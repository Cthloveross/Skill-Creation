---
name: california-small-claims-pdf-filler
description: Inspect and fill a supplied California Small Claims Court PDF (including SC-100-style AcroForms) from a case description. Use when a blank court form must be populated conservatively, saved as a new PDF, and semantically verified after reopening.
---

# California Small Claims PDF Filler

Use this Skill to prepare a filled copy of a supplied interactive court PDF. It is intentionally conservative: populate only facts expressly provided, do not invent legal conclusions, and leave clerk/court, hearing, case-number, fee-waiver, optional, and unmentioned fields blank.

## Prerequisites

* The source PDF must exist and be readable.
* Python must have `pypdf` available. The scripts report a clear error if it is unavailable.
* The destination must be a distinct writable path. Never overwrite the supplied blank template.
* The PDF must contain an AcroForm. XFA-only forms are reported as unsupported because their values cannot be safely written with this Skill.

## Procedure

1. Inspect the actual supplied PDF before choosing any field names or checkbox values. Do not assume that another revision of SC-100 has the same field paths or button states.

   ```bash
   python3 scripts/inspect_pdf.py <<'JSON'
   {"source_pdf":"/path/to/blank.pdf","include_page_text":true}
   JSON
   ```

   The JSON result lists field names, form types, current values, choice options, discovered button states, page/widget locations, and extracted page text. Use the names and states from this result exactly.

2. Extract only the stated facts from the case description. For an SC-100-like claim, normally map facts to the plaintiff identity/contact and address, defendant identity/address (and phone only if the actual form has a relevant nonoptional field), claim amount, concise reason for claim, event dates, and an expressly requested filing/date field. Render every entered date as `YYYY-MM-DD`.

   Use neutral, factual claim language. For example, preserve the supplied basis (such as a contract), amount, relevant period, and stated demand attempts; do not add remedies, interest, statutes, service facts, citizenship, court venue names, or assertions not given. A statement that the claimant is filing where the defendant lives may support the matching venue/residency selection only if the form explicitly presents that selection and its wording matches the stated fact.

   A provided filing date is not authorization to create a signature. Leave handwritten/electronic signature fields empty unless the task explicitly directs execution of a signature and the execution environment has an authorized signing method.

3. Build an `assignments` object containing **only** selected, nonempty fields. Keys are the inspected fully qualified field names. Values are strings, except checkbox/radio values, which must be the exact non-off state reported by the inspector. Do not write an empty-string assignment merely to clear an optional field.

4. Fill and verify in one operation:

   ```bash
   python3 scripts/fill_pdf.py <<'JSON'
   {
     "source_pdf":"/path/to/blank.pdf",
     "output_pdf":"/path/to/filled.pdf",
     "assignments": {
       "actual.text.field.name":"Fact stated in the case description",
       "actual.button.field.name":"ActualOnStateFromInspection"
     }
   }
   JSON
   ```

   The script copies the original document structure, writes supplied AcroForm values, saves a new file, reopens it, and returns `verified: true` only when every requested semantic form value can be read back. Treat any failure, unknown field, unsupported form, or `verified: false` as a stop condition; correct the mapping rather than guessing.

5. Confirm that the reported output path is the requested deliverable (for this task, `/root/sc100-filled.pdf`). Keep the blank original unchanged. The saved output must be the artifact delivered to the user.

## Script JSON contracts

`scripts/inspect_pdf.py` input:

```json
{"source_pdf":"string path", "include_page_text":true}
```

It emits either `{"ok":true,"form_type":"AcroForm", "fields":[...], "pages":[...]}` or `{"ok":false,"error":"..."}`. `include_page_text` defaults to false.

`scripts/fill_pdf.py` input:

```json
{"source_pdf":"string path", "output_pdf":"string path", "assignments":{"fully.qualified.field":"value"}}
```

It emits either a success object containing the output path, requested values, read-back values, and `verified`, or an error object. It does not make banking, filing, signing, or court-submission actions.

## Validation checklist

Before final delivery, ensure that the fill script returned `ok: true` and `verified: true`; that its `read_back` values match the intended facts; that every checkbox value is one of the inspector's available on-states; that all entered dates use `YYYY-MM-DD`; and that no court-completed, case-number, hearing, clerk, optional, or unmentioned field was included in `assignments`.
