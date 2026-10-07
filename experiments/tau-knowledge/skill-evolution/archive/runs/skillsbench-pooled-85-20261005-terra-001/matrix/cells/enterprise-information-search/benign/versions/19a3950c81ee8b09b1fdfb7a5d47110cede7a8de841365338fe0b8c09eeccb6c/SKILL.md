---
name: enterprise-export-retrieval
description: Retrieve evidence-based answers to keyed natural-language questions from heterogeneous JSON enterprise exports and write a validated answer.json artifact. Use when data, questions, and required output paths are supplied at runtime.
---

# Enterprise Export Retrieval

Investigate the supplied enterprise files at runtime. Do not assume a vendor schema, product-to-file mapping, person identifier format, or that a mention proves authorship, review, attendance, or contribution.

## Required artifact

Read the supplied question file and create the requested output file (normally `/root/answer.json`). The top-level object must contain exactly every labelled question key. Every question entry has exactly:

- `answer`: a list, including for singleton names, IDs, items, counts, or values;
- `tokens`: a non-negative numeric JSON value or numeric string.

Token placeholders such as `not_available` are invalid. Pass the execution agent's per-question token accounting to the writer when available. If no separate accounting facility exists, use numeric `0`, never a text placeholder.

## Workflow

1. Read the question file. For each key, identify the target entity, requested relation/value, time or version constraints, and expected value type.
2. Discover the actual export structure before searching:
   ```sh
   echo '{"root":"/root/DATA"}' | python3 scripts/discover_json.py
   ```
   Inspect metadata and authoritative records for stable IDs, aliases, product mappings, and timestamp semantics.
3. Locate candidate evidence with the question file:
   ```sh
   echo '{"root":"/root/DATA","question_path":"/root/question.txt"}' | python3 scripts/search_json.py
   ```
   The search output is an evidence locator, not an answer generator. Use exact IDs, names, URLs, dates, or relation terms for narrower follow-up queries when needed.
4. For each proposed answer, retain a ledger of source/path, directly attributed action or value, target entity, and applicable date/version. Follow cross-references into authoritative records. Resolve identities using stable metadata where possible. Exclude candidates supported only by co-occurrence, membership, acknowledgements, or unrelated versions.
5. Deduplicate according to the question predicate and verify all temporal and version wording. Return only values with direct support; do not fabricate unsupported answers.
6. Write the completed answers. `answers` must map every question key to a list. Supply a numeric scalar or a numeric per-key object in `tokens`:
   ```sh
   echo '{"questions_path":"/root/question.txt","output_path":"/root/answer.json","answers":{},"tokens":0}' | python3 scripts/write_answer.py
   ```
   Replace the empty mapping with the runtime-derived answer lists before running this command. Then validate:
   ```sh
   echo '{"answer_path":"/root/answer.json","questions_path":"/root/question.txt"}' | python3 scripts/validate_answer.py
   ```

## Script interfaces

All scripts receive one JSON object on stdin and emit one JSON object on stdout; they use only the Python standard library.

- `discover_json.py`: input `{root, max_files?, max_paths?}`; inventories JSON files, root shapes, field paths, and scalar examples.
- `search_json.py`: input `{root, question_path? | questions? | queries?, max_hits_per_question?}`; returns lexical evidence with source file, JSON path, match terms, value, and parent-record preview.
- `write_answer.py`: input `{answers, output_path?, questions_path?, tokens?}`; validates list answers, exact question-key coverage when a question path is supplied, and numeric non-negative token values before atomically writing the artifact. Its default token value is numeric `0`.
- `validate_answer.py`: input `{answer_path, questions_path?}`; reports structural, key, list-shape, and token-format violations without deciding factual correctness.

## Failure handling

Unreadable JSON, missing files, ambiguous aliases, and conflicting evidence require further investigation, not guessing. Do not modify the question file or supplied data files. If the task specifies a missing-data convention, apply it only where supported; otherwise report the ambiguity to the execution agent rather than inventing a textual answer.