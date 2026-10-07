---
name: offer-letter-generator
description: Fill placeholders in a Word (.docx) offer-letter template from a JSON data file and evaluate a relocation conditional block, writing a valid .docx. Use when a task supplies an OOXML template with {{PLACEHOLDER}} tokens and {{IF_...}}...{{END_IF_...}} regions that must be resolved while preserving document structure, styles, headers/footers, and relationships.
---

# Offer Letter / OOXML template filler

## When to use
A Word document is a ZIP of XML parts. The visible text of a placeholder such as
`{{CANDIDATE_FULL_NAME}}` is frequently split across several `<w:t>` runs, and
conditional markers (`{{IF_RELOCATION}}` / `{{END_IF_RELOCATION}}`) may sit in
the same paragraph or span several paragraphs. This Skill resolves both while
keeping the rest of the package (styles, relationships, headers, footers,
tables, text boxes) intact instead of rebuilding the file.

## Public task contract (this instance)
- Inputs (already copied into the container):
  - `/root/employee_data.json` — flat JSON of `KEY: value` pairs. Each key maps
    to a `{{KEY}}` placeholder. The key `RELOCATION_PACKAGE` drives the
    conditional block.
  - `/root/offer_letter_template.docx` — the template.
- Output: `/root/offer_letter_filled.docx`.
- Rules:
  - Replace every `{{KEY}}` with the string form of its JSON value.
  - Conditional `{{IF_RELOCATION}}...{{END_IF_RELOCATION}}`: KEEP the enclosed
    content (removing only the two markers) when `RELOCATION_PACKAGE` is `Yes`;
    otherwise REMOVE the markers AND the enclosed content.
  - No `{{...}}` placeholder or IF/END control marker may remain anywhere in the
    saved document, and the document must still open as a valid .docx.

## Method (what the script does)
1. Load the JSON data. Compute `keep = RELOCATION_PACKAGE in {Yes,Y,True,1}`
   (case-insensitive).
2. Open the template ZIP. Only parts that end in `.xml` and actually contain
   `{{` are parsed/edited (so `styles.xml`, media, etc. are copied byte-for-byte
   and never risk namespace churn).
3. For each edited part:
   - Handle the conditional first, at paragraph (`w:p`) granularity so text is
     never bled across paragraph boundaries:
     * markers in one paragraph → operate inline on that paragraph's combined
       text;
     * markers spanning paragraphs → keep: strip the markers from the two edge
       paragraphs; remove: trim the edge paragraphs to the text outside the
       markers, delete the fully-enclosed middle paragraphs, and drop an edge
       paragraph entirely if it becomes empty.
   - Then replace placeholders per paragraph: concatenate the paragraph's `<w:t>`
     runs into one logical string, substitute `{{KEY}}` tokens, and redistribute
     the result back across the existing runs (preserving run count and
     `xml:space="preserve"`). This correctly resolves placeholders that are
     split across runs.
4. Re-serialize edited parts, re-injecting any `xmlns:*` declarations that were
   present on the original root element (so `mc:Ignorable` prefixes such as
   `w14` survive), and prepend the standalone XML declaration.
5. Rewrite the ZIP preserving every original entry's metadata and compression,
   substituting only the edited parts.
6. Re-open the written file and scan all `.xml` parts for leftover `{{...}}`
   tokens and IF/END markers; report them.

Fidelity note: when a placeholder or conditional edit changes text, the
redistribution packs text into the existing runs in order; this preserves
paragraph structure and is sufficient for text-content correctness. The script
handles a single relocation conditional block (the template's case); if a part
contains more than one block only the first is processed — inspect output if the
scan still reports markers.

## Running it
The entrypoint reads a JSON config from stdin and writes a JSON report to
stdout. All paths default to the task locations, so an empty object works:

```
python3 /app/environment/skills/current/scripts/run_fill.py <<'JSON'
{}
JSON
```

Override paths explicitly if needed:
```
echo '{"data_path":"/root/employee_data.json","template_path":"/root/offer_letter_template.docx","output_path":"/root/offer_letter_filled.docx"}' | \
  python3 /app/environment/skills/current/scripts/run_fill.py
```

Input schema: `{data_path?, template_path?, output_path?}` (all optional).
Output schema:
```
{"status":"ok"|"warning"|"error",
 "output_path":str,
 "relocation_kept":bool,
 "edited_parts":[str,...],
 "unresolved_placeholders":[str,...],
 "leftover_markers":[str,...],
 "message":str}
```
`status` is `ok` only when the output exists, no `{{...}}` token remains, and no
IF/END marker remains. `warning` means leftovers were found; `error` means the
run failed (see `message`).

## Executor workflow
1. Inspect the real inputs first: `python3 - <<'PY'` reading
   `/root/employee_data.json`, and list the template keys/markers if useful.
2. Run the entrypoint as above.
3. Confirm the stdout report has `status == "ok"` and empty
   `unresolved_placeholders` / `leftover_markers`. If placeholders are listed,
   they correspond to `{{KEY}}` tokens whose `KEY` is absent from the JSON —
   recheck the data file for the exact key spelling.
4. Optionally run the validator for an independent check of the saved file:
   ```
   echo '{"path":"/root/offer_letter_filled.docx"}' | \
     python3 /app/environment/skills/current/scripts/validate.py
   ```
   It reports `valid_zip`, `opens` (parses all xml parts), and any leftover
   tokens/markers.
5. The deliverable is the `.docx` at `/root/offer_letter_filled.docx`; the
   entrypoint must regenerate it, not rely on a pre-existing file.

## Failure handling
- Missing input file → `status:error` with a clear message; verify the copied
  paths exist (`ls /root`).
- A placeholder key missing from JSON → listed under
  `unresolved_placeholders`; the token is left in place rather than guessed.
- An XML part that fails to parse is left unchanged (copied verbatim) and noted;
  this avoids corrupting unrelated parts.
- Only standard-library modules (`zipfile`, `xml.etree.ElementTree`, `json`,
  `re`) are used, so no package install is required.

See `references/ooxml-template-basics.md` for the underlying rationale.
