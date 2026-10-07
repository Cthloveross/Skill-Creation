---
name: california-small-claims-pdf-filler
description: Inspect and conservatively complete a supplied California Small Claims Court PDF (including SC-100-style AcroForms), save a new filled PDF, and verify that all stated party, address, claim, demand, and date facts survive reopening. Use when an interactive court form must be completed from a case description without inventing facts.
---

# California Small Claims PDF Filler

Use this Skill to prepare a filled copy of a supplied interactive court PDF. Populate only facts expressly stated in the case description. Leave court/clerk, case-number, hearing, fee-waiver, optional, signature, and unmentioned fields blank.

## Prerequisites

* The source PDF exists and is readable, and the destination is a distinct writable path.
* Python has `pypdf` installed.
* The source has an AcroForm. XFA-only forms are unsupported because this Skill cannot safely write their values.
* Do not overwrite the blank source PDF.

## Required method

1. **Inspect the actual supplied PDF first.** Field names, widget locations, radio-button states, and form revisions vary. Never reuse assumed SC-100 field paths or button states.

   ```bash
   python3 scripts/inspect_pdf.py <<'JSON'
   {"source_pdf":"/root/sc100-blank.pdf","include_page_text":true}
   JSON
   ```

   The report contains every logical field, its type, current value, options, available non-`Off` button states, and widget page/rectangle. Match fields to nearby form labels using this report and the PDF itself.

2. Extract only the supplied facts and map them to supported fields. For a party listing, enter the name, street address, **city, state, and ZIP in their separate fields**, telephone, and email when supplied and when the form presents a relevant field. Do not place the entire address only in the street-address field. If both parties have full addresses, complete all separate address components for each party.

3. Draft a concise factual claim explanation in the form's reason/details field(s). It must preserve each stated material fact rather than relying on a field label to imply it. In particular, include the claimed amount; the stated security-deposit, roommate-sublease, and signed-contract basis; the failure to return the deposit; the stated incident period; and any stated demand attempts, communication method (for example, text messages), and lack of response. Use additional supported claim-detail fields if the main explanation field is too short; do not omit supplied demand/nonresponse facts just to shorten the narrative.

4. Render every entered date as `YYYY-MM-DD`. A requested filing date is not authorization to create a signature: leave signature fields blank unless the task explicitly authorizes an available signing method. A venue/residency or first-time-claimant selection may be set only when the form explicitly presents that selection and its wording matches a stated fact. For buttons, use exactly an inspected non-`Off` state.

5. Create `assignments` containing only selected, nonempty form fields. Keys must be inspected fully-qualified field names. Values are strings, except multi-select fields may use lists of strings. Do not assign empty strings merely to clear fields.

6. Fill the PDF and confirm direct semantic read-back:

   ```bash
   python3 scripts/fill_pdf.py <<'JSON'
   {
     "source_pdf":"/path/to/blank.pdf",
     "output_pdf":"/path/to/filled.pdf",
     "assignments":{"inspected.field.name":"stated fact"}
   }
   JSON
   ```

   `fill_pdf.py` copies the source structure, writes the requested AcroForm values, saves a new PDF, reopens it, and compares the requested and read-back values. An unknown field, unsupported PDF, `ok: false`, or `verified: false` is a stop condition: correct the field mapping instead of guessing.

7. **Validate completeness after filling.** Read-back alone only proves that supplied assignments were saved; it cannot identify a fact omitted from `assignments`. Supply all material fact fragments that must be observable in the finished PDF, including a combined city/state/ZIP fragment for each party and distinctive words from the demand/nonresponse statement.

   ```bash
   python3 scripts/validate_pdf.py <<'JSON'
   {
     "pdf":"/path/to/filled.pdf",
     "required_fragments":["required fact 1","required fact 2"]
   }
   JSON
   ```

   The validator searches both extractable page text and AcroForm names/values after reopening. It emits `complete: true` only if every requested fragment is observable after whitespace and punctuation normalization. If a fragment is absent, inspect the form again and populate the correct separate field or claim-detail field. Do not deliver until this check and fill-script verification both succeed.

8. Confirm the output path is the required deliverable (for the current task, `/root/sc100-filled.pdf`) and that the blank original remains unchanged.

## JSON contracts

### `scripts/inspect_pdf.py`

Input:

```json
{"source_pdf":"string path", "include_page_text":true}
```

Output is either `{"ok":true,"form_type":"AcroForm","fields":[...],"semantic_values":{...}}` or `{"ok":false,"error":"..."}`.

### `scripts/fill_pdf.py`

Input:

```json
{"source_pdf":"string path","output_pdf":"string path","assignments":{"fully.qualified.field":"nonempty value"}}
```

Output contains `requested`, `read_back`, `mismatches`, and `verified`. The script does not sign, file, submit, or otherwise take court action.

### `scripts/validate_pdf.py`

Input:

```json
{"pdf":"string path","required_fragments":["nonempty required text", "another required text"]}
```

Output lists found and missing fragments plus text-source diagnostics. Matching is case-insensitive and ignores punctuation/whitespace, so a separately displayed city, state, and ZIP can be checked as one logical fragment.

## Final checklist

* Every stated party has each available, supplied contact and separate address component populated.
* The claim narrative includes the factual basis, amount, date period, return failure, and supplied demand/communication/nonresponse facts.
* All dates are literal `YYYY-MM-DD` values.
* The fill result reports `ok: true` and `verified: true`.
* The completeness validator reports `complete: true` for all material supplied facts.
* No court-only, optional, unsupported, or unmentioned fields were assigned.
