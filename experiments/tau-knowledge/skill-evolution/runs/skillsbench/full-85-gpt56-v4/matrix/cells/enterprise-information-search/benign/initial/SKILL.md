---
name: enterprise-json-evidence-retrieval
description: Retrieve answers to keyed natural-language questions from a directory of heterogeneous enterprise JSON exports. Use when questions are in a text or JSON file and the required deliverable is a JSON answer file with list-valued answers and per-question token metadata.
---

# Enterprise JSON evidence retrieval

Use this Skill to investigate the actual supplied dataset before answering. It deliberately does not assume a vendor schema, product names, person identifiers, or a fixed relationship between product and metadata files.

## Runtime inputs and deliverable

The usual runtime inputs are a JSON-data directory (for example `/root/DATA`) and a keyed question file (for example `/root/question.txt`). The required deliverable in this task family is `/root/answer.json`.

Each answer must be based on direct evidence for the relation requested by its question. Do not treat meeting attendance, a mention, a team roster, or a nearby link as authorship/review/contribution unless the question asks for that relation or the record explicitly attributes that action.

## Procedure

1. **Read the questions and preserve their keys.** Inspect the complete question file. Determine whether it is a JSON object or keyed text. Keep every key exactly; do not invent answer keys.
2. **Discover the export schema.** Run `scripts/retrieve.py` in `discover` mode. Identify which files contain communications/documents versus authoritative employee, customer, or team metadata. Inspect key names and samples instead of assuming them.
3. **Search narrowly, then expand.** For each question, run `search` with distinctive entities from the question (product names, organization names, IDs, dates, uncommon phrases). Search aliases separately when discovery exposes them. Results include file and JSON-pointer provenance plus a compact containing record.
4. **Read decisive records.** Use `get` with a result's `file` and `pointer` to inspect the full value and neighboring metadata. Follow IDs, participants, document links, and employee metadata only when they establish the requested relation. Keep a small ledger of candidate answer -> source pointer -> explicit attributed action.
5. **Resolve identities carefully.** Use stable employee/customer IDs or emails where available. Map them to requested display names only after corroborating the corresponding metadata. Do not merge people merely because their names are similar.
6. **Apply time/version constraints.** Distinguish creation, revision, message, meeting, and closure times. Include evidence only in the question's stated time/version scope.
7. **Construct and validate the artifact.** Supply the final researched answers to `write_answer.py`; it normalizes every answer to a list and writes `/root/answer.json`. Then run `validate_answer.py`. Fix schema errors and revisit unsupported candidates before considering the work complete.

## Commands

All scripts accept one JSON object on standard input and emit a JSON object on standard output. They use only the Python standard library.

Discover files and recurring JSON keys:

```sh
python /app/environment/skills/current/scripts/retrieve.py <<'JSON'
{"mode":"discover","data_root":"/root/DATA"}
JSON
```

Search all JSON text leaves. `file_contains` is optional and is useful after discovery to limit a product or metadata file.

```sh
python /app/environment/skills/current/scripts/retrieve.py <<'JSON'
{"mode":"search","data_root":"/root/DATA","query":"distinctive entity or exact phrase","max_results":40,"file_contains":""}
JSON
```

Read an untruncated record from a prior search result. JSON pointers use standard escaping (`~1` for `/`, `~0` for `~`).

```sh
python /app/environment/skills/current/scripts/retrieve.py <<'JSON'
{"mode":"get","file":"/root/DATA/path/from/search.json","pointer":"/records/0"}
JSON
```

Write researched answers. `answers` may contain a scalar or list, but the writer always serializes a list. `token_counts` values are serialized as strings. Record the executor's actual per-question token count when it is available; otherwise use `"0"` rather than fabricating a measurement.

```sh
python /app/environment/skills/current/scripts/write_answer.py <<'JSON'
{"questions_path":"/root/question.txt","output_path":"/root/answer.json","answers":{"q1":["researched value"]},"token_counts":{"q1":"0"}}
JSON
python /app/environment/skills/current/scripts/validate_answer.py <<'JSON'
{"questions_path":"/root/question.txt","answer_path":"/root/answer.json"}
JSON
```

## Script interfaces

- `retrieve.py`
  - `discover`: input `{"mode":"discover","data_root":str}`; output has `files`, each file's top-level type/count, and recursive key frequencies.
  - `search`: input `{"mode":"search","data_root":str,"query":str,"max_results":int? ,"file_contains":str?}`; output has query terms and ranked results. Every result has `file`, `pointer`, `matched_text`, `score`, and `context`; these are evidence leads, not answers.
  - `get`: input `{"mode":"get","file":str,"pointer":str,"max_chars":int?}`; output has the value at that pointer. It refuses files outside the supplied data root when `data_root` is also provided.
- `write_answer.py`: input `{"questions_path":str,"output_path":str,"answers":object,"token_counts":object?}`; output reports written keys and path. It fails if a question key has no supplied answer, which prevents accidentally returning a partial answer file.
- `validate_answer.py`: input `{"questions_path":str,"answer_path":str}`; output is `{"valid":true,...}` or `{"valid":false,"errors":[...]}` and exits nonzero for invalid output.

Validation establishes only output shape, key coverage, JSON validity, list answer shape, and string token fields. Semantic validation remains the evidence-ledger review above.
