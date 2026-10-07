---
name: enterprise-json-evidence-retrieval
description: Retrieve answers to keyed natural-language questions from a runtime-supplied enterprise JSON corpus. Use when questions are in a text/JSON file and the required deliverable is a validated answer.json with list-valued answers and per-question token logging.
---

# Enterprise JSON Evidence Retrieval

Use this Skill to investigate the supplied corpus at runtime. Do not assume a product-to-file mapping, JSON field paths, identity mappings, timestamps, or that proximity in a record establishes authorship, review, participation, or another requested relation.

## Inputs and deliverable

The executor receives the data directory and a question file from the task environment. Read the complete question file first and preserve its exact question keys. The final artifact must be written to the requested output path (normally `/root/answer.json`) and have this shape for every key:

```json
{"q1":{"answer":["value"],"tokens":"..."}}
```

Every `answer` is an array, including a one-item answer. Answer items may be strings, numbers, or other JSON values only when the question and discovered schema call for that type. `tokens` is a string. Do not invent a consumption value: use execution telemetry if available; otherwise record `"unavailable"`.

## Investigation workflow

1. **Parse the questions.** Identify the requested entity, relation, constraints (especially time/version), requested identifier/display form, and whether a value is a measurement, name, ID, or collection. Do not confuse the question labels with answers.
2. **Discover schemas.** Run `scripts/inventory_json.py` against the actual data root. Inspect the relevant file structures and metadata before deciding which fields are IDs, names, record text, participants, timestamps, or links.
3. **Search iteratively.** Use `scripts/search_json.py` with several small, question-derived term sets. Search exact entities first and then useful semantic variants. The script returns record paths, matching leaves, and previews; inspect a returned record in full with `scripts/read_json_path.py` when necessary.
4. **Establish evidence rather than co-occurrence.** For each candidate answer, retain a mental or written ledger containing source file, JSON path, the explicit attributed action/value, target entity, and relevant temporal/version context. Resolve people through metadata stable IDs and corroborating fields. Exclude a person merely mentioned, on a team, copied on a message, or attending an unrelated meeting.
5. **Verify and normalize.** Re-read the wording. Deduplicate answer values only after retaining the supporting evidence, resolve conflicts using source and version context, and ensure requested display names versus IDs are correct.
6. **Write the artifact.** Supply the completed mapping to `scripts/write_answer.py`. It derives/validates question keys when possible, rejects non-list answers, and atomically writes valid JSON.

## Script calls

All scripts accept one JSON object on stdin and emit one JSON object on stdout. Run them from the Skill package root, for example:

```bash
python scripts/inventory_json.py <<'JSON'
{"data_root":"/root/DATA","max_paths_per_file":80}
JSON

python scripts/search_json.py <<'JSON'
{"data_root":"/root/DATA","queries":[{"id":"q1","terms":["target phrase","review"],"logic":"all"}],"max_hits_per_query":30}
JSON
```

`search_json.py` schema:

- Input: `data_root` (directory), `queries` (nonempty array of `{id, terms, logic?}`), optional `max_hits_per_query`, `preview_chars`, and `include_root_records`.
- `terms` are case-insensitive literal phrases. `logic` is `"all"` (default) or `"any"`.
- Output: `results` keyed by query ID. Each hit has `file`, `record_path` (a JSON path array), `matched_leaves`, and a bounded preview. Paths can be passed unchanged to `read_json_path.py`.

Read a returned record with:

```bash
python scripts/read_json_path.py <<'JSON'
{"file":"/root/DATA/products/example.json","path":["records", 0],"max_chars":30000}
JSON
```

Finish only after materializing the actual output file:

```bash
python scripts/write_answer.py <<'JSON'
{
  "question_file":"/root/question.txt",
  "output_file":"/root/answer.json",
  "answers":{"q1":["resolved value"],"q2":[]},
  "tokens":{"q1":"unavailable","q2":"unavailable"}
}
JSON
```

The writer validates that the answer key set matches detected question keys (or an explicitly supplied `question_keys` list), that every answer is an array, and that every token value is a string. Its stdout is a summary, not a substitute for the required output file.

## Failure handling

If a JSON file cannot be parsed, inventory/search report it in `errors`; do not silently treat it as evidence. If search is overbroad, add distinctive entity terms or narrow through inspected schemas rather than trusting snippets. If question keys cannot be reliably parsed from a nonstandard question file, pass the exact keys in `question_keys` to the writer. If the corpus provides no direct support for an answer, do not infer it from related records; use an empty list only when that is the supported result.
