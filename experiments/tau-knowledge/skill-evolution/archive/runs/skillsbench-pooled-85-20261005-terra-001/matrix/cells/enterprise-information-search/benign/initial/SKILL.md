---
name: enterprise-export-retrieval
description: Retrieve answers to keyed natural-language questions from heterogeneous JSON enterprise exports. Use when a task provides a data directory, a question file, and requires a typed JSON answer artifact with evidence-based identity, authorship, temporal, and cross-reference reasoning.
---

# Enterprise Export Retrieval

Use this skill to investigate the supplied dataset at runtime. It deliberately does not assume a vendor schema, a product/file mapping, or a fixed meaning for fields such as `author`, `user`, or `id`.

## Inputs and required artifact

The usual task inputs are a JSON export directory (for example `/root/DATA`) and a keyed question file (for example `/root/question.txt`). The final artifact must be created at the path specified by the task (normally `/root/answer.json`). Its top-level keys must be the question keys, and every value must contain at least `answer` and `tokens`.

`answer` must retain the semantic JSON type requested by the question. Lists of names, items, or IDs remain arrays even for one item; counts and measurements remain numbers unless the question explicitly asks for text. Do not invent a token total: use a runtime-provided accounting value when available, otherwise use the explicit string `"not_available"`.

## Procedure

1. Read the question file first. Determine every key, entity, requested relation, time/version condition, and answer type. `scripts/search_json.py` accepts either a `questions` object or a question file whose contents are JSON, Python-literal mappings, `q1: question` lines, or numbered question lines.
2. Inspect schemas before deciding which files matter. Run:
   ```sh
   echo '{"root":"/root/DATA"}' | python3 scripts/discover_json.py
   ```
   Review root types, recurring field paths, errors, and representative scalar fields. Check metadata files for authoritative identity and product/customer mappings before resolving names in product records.
3. Perform focused retrieval for each question rather than treating a keyword hit as an answer. For a question file, run:
   ```sh
   echo '{"root":"/root/DATA","question_path":"/root/question.txt","max_hits_per_question":80}' | python3 scripts/search_json.py > /tmp/candidates.json
   ```
   For a more precise pass, supply an entity name, ID, URL fragment, date, or phrase in `queries`, e.g. `{"root":"/root/DATA","queries":{"q1":"exact entity and relation"}}`. The script reports source file, JSON path, matching text, and immediate-record preview; it is an evidence locator, not an answer oracle.
4. Follow IDs, URLs, filenames, employee aliases, and product references from a candidate into their authoritative records. Build a small candidate-to-evidence ledger for each answer: candidate, source/path, exact attributed action or value, target entity, and relevant time/version. Resolve people using stable IDs and metadata when possible. Do not equate attendance, mention, or membership with authorship/review/contribution unless the question asks for that relation.
5. Apply all temporal wording to the timestamps and versions actually discovered. Exclude evidence concerning a similarly named product, another version, or an irrelevant time interval. Deduplicate by the requested entity/value, not merely by matching text.
6. Assemble the final values only after checking every candidate against the question predicate. Use the writer to produce and structurally validate the artifact:
   ```sh
   echo '{"questions_path":"/root/question.txt","output_path":"/root/answer.json","answers":{"q1":["example value"]},"tokens":"not_available"}' | python3 scripts/write_answer.py
   ```
   Replace the example value with findings; do not include explanations or provenance in `answer` unless requested. For distinct per-question accounting, pass `tokens` as an object keyed by question ID. Run `scripts/validate_answer.py` on the completed artifact before submission.

## Script interfaces

All packaged scripts read one JSON object from stdin and emit one JSON object to stdout. They use only the Python standard library.

- `discover_json.py`: input `{root, max_files?, max_paths?, max_examples?}`. Output `{root, files:[{file, bytes, root_type, root_keys, observed_paths, examples, error?}], errors}`. It inventories JSON schemas without relying on an assumed layout.
- `search_json.py`: input `{root, queries? | questions? | question_path?, max_hits_per_question?, max_preview_chars?}`. Output `{queries, results:{key:[evidence...]}, errors}`. Evidence has `file`, `path`, `score`, `matched_terms`, `value`, and `record_preview` when available. Search terms are intentionally broad; inspect context and source schema before using a hit.
- `write_answer.py`: input `{answers, output_path?, questions_path?, tokens?}`. `answers` maps question keys to already-derived JSON values. It writes the required mapping atomically and returns a validation report. If a question file is supplied, it rejects missing or extra keys.
- `validate_answer.py`: input `{answer_path, questions_path?}`. Output reports JSON validity, key mismatches, missing fields, and suspicious answer shapes. It does not decide semantic correctness.

## Failure handling

Treat unreadable JSON, missing files, unresolved identity aliases, and ambiguous evidence as investigation failures, not permission to guess. Search with stable identifiers and inspect the relevant raw records. If an answer is genuinely unsupported, use the task's prescribed missing-answer convention; if none exists, surface the ambiguity to the execution agent rather than fabricating a value. Never claim that a script's lexical score proves authorship, review, approval, or a time condition.
