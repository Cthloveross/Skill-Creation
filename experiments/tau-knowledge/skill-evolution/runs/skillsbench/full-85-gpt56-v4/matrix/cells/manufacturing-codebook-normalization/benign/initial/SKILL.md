---
name: manufacturing-defect-codebook-normalizer
description: Normalize manufacturing-test reason text from a CSV into product-scoped controlled-codebook entries, preserving verbatim evidence spans and routing weak or ambiguous matches to UNKNOWN. Use when logs and one or more product codebook CSV files are supplied and a solution.json-style record output is required.
---

# Manufacturing defect codebook normalizer

Use this Skill to produce a deterministic, traceable normalization file from the supplied runtime data. It is deliberately conservative: it never selects a code outside the event's product namespace, applies declared station scope when present, and emits `UNKNOWN` rather than treating a weak fuzzy string score as proof.

## Procedure

1. Inspect the supplied log and codebook CSV headers if an input schema is unclear. The normalizer discovers common semantic roles (record ID, product, station, engineer, raw reason, code, label, aliases, and optional scope) and reports an actionable error if required roles cannot be resolved. Provide explicit `log_roles` or `codebook_roles` only when the automatic role resolution is genuinely ambiguous.
2. Run the packaged entrypoint. With the paths in the task environment, use:

   ```sh
   python3 /app/environment/skills/current/scripts/normalize.py <<'JSON'
   {"logs_path":"/app/data/test_center_logs.csv","codebook_glob":"/app/data/codebook_*.csv","output_path":"/app/output/solution.json"}
   JSON
   ```

   The script reads one JSON configuration object from stdin and writes a compact JSON execution summary to stdout. It writes the required result document to `output_path`.
3. Inspect the stdout summary and the generated JSON. If the input has product identifiers not represented by any codebook, do not substitute a similarly named product; the records will be emitted with `UNKNOWN` predictions. If role resolution fails, correct the role mapping in the invocation rather than editing source records.
4. The script validates output coverage, product codebook membership, station compatibility where declared, segment IDs, literal source spans, confidence bounds, UNKNOWN fields, and required output shape before saving. Treat a validation failure as a data/schema issue to resolve, not as permission to weaken namespace constraints.

## Matching and calibration

The entrypoint preserves the original raw reason text. It creates spans only from literal slices of that text, primarily separating strong list boundaries (newlines and semicolons). Candidate retrieval uses normalized Unicode/whitespace text only internally and combines exact/containment alias matches, token overlap, character similarity, digit-reference agreement, product scope, and optional station filtering. Labels, descriptions, and keyword/alias fields from the codebook become candidate aliases; code, product, and station fields are not treated as defect aliases.

`accept_score` (default `0.70`) and `ambiguity_margin` (default `0.055`) are explicit operating-policy parameters, not universal claims about fuzzy matching. An otherwise plausible candidate below the threshold or too close to a runner-up becomes `UNKNOWN` with an evidence-bearing rationale. Accepted confidences derive from the same score and separation evidence; UNKNOWN confidences are capped below every accepted confidence. This gives varied engineering diagnostics without claiming statistical calibration that the supplied data cannot establish.

## Entrypoint input schema

`normalize.py` accepts a JSON object with these fields:

- `logs_path`: required log CSV path (default `/app/data/test_center_logs.csv`).
- `codebook_glob`: glob for codebook CSVs (default `/app/data/codebook_*.csv`).
- `codebook_paths`: optional explicit array of codebook paths, overriding the glob.
- `output_path`: output JSON path (default `/app/output/solution.json`).
- `accept_score`: optional number in `[0,1]` (default `0.70`).
- `ambiguity_margin`: optional nonnegative number (default `0.055`).
- `log_roles`: optional map with any of `record_id`, `product_id`, `station`, `engineer_id`, `raw_reason_text` mapped to exact CSV header names.
- `codebook_roles`: optional map with any of `code`, `label`, `product_id`, `station` mapped to exact codebook header names. Alias-bearing columns are otherwise inferred from the remaining textual fields.

The output file has the task-required top-level `records` array and records preserve the selected input fields verbatim. Each normalized item has `<record_id>-S<i>` identifiers, a nonempty verbatim `span_text`, a valid code and label or `UNKNOWN`/empty label, numeric confidence, and an evidence-based rationale.
