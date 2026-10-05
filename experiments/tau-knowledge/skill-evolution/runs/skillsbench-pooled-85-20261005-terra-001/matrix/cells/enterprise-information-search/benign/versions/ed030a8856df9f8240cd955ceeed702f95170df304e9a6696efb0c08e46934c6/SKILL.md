---
name: enterprise-export-retrieval
description: Retrieve evidence-based answers to keyed natural-language questions from heterogeneous JSON enterprise exports and write a validated answer.json artifact. Use when data, questions, and required output paths are supplied at runtime.
---

# Enterprise Export Retrieval

Investigate supplied enterprise files at runtime. Do not assume a vendor schema, product-to-file mapping, person identifier format, or that a mention proves authorship, review, attendance, or contribution.

## Required artifact

Read the supplied question file and create the requested output file (normally `/root/answer.json`). The top-level object must contain exactly every labelled question key. Every question entry has exactly:

- `answer`: a list, including singleton names, IDs, items, counts, or values;
- `tokens`: a non-negative numeric JSON value or numeric string.

Token placeholders such as `not_available` are invalid. Pass the execution agent's per-question token accounting to the writer when available. If no separate accounting facility exists, use numeric `0`, never a text placeholder.

## Workflow

1. Read the question file. For each key, identify its target entity, requested relation/value, time or version constraints, and requested output type.
2. Discover the actual export structure before searching:
   ```sh
   echo '{"root":"/root/DATA"}' | python3 scripts/discover_json.py
   ```
   Inspect authoritative metadata for stable IDs, aliases, product mappings, and timestamp semantics.
3. Locate initial evidence:
   ```sh
   echo '{"root":"/root/DATA","question_path":"/root/question.txt"}' | python3 scripts/search_json.py
   ```
   This is an evidence locator, not an answer generator. Use IDs, names, URLs, dates, relation labels, and target terms from its results for narrower follow-up inspection.
4. Build a candidate-to-evidence ledger. For every proposed item retain source/path, exact attributed action or value, target entity, and applicable date/version. Follow cross-references into authoritative records.
5. **Person, author, and reviewer answers require direct relation evidence.** A person ID or name is valid only if either:
   - a bounded record contains the candidate and an explicit requested-relation field/action (for example `author`, `reviewer`, `reviewed_by`); or
   - a bounded relation record contains an explicit stable identity value, and authoritative metadata explicitly maps that same value to the returned display name.

   Do not return an employee merely because the ID appears in employee metadata, a team roster, a meeting, or unrelated discussion. Do not treat arbitrary prose in a record as an identity alias. In particular, if an ID cannot be found in a record containing the requested author/reviewer relation, remove it rather than guessing.

   Check proposed people before writing:
   ```sh
   echo '{"root":"/root/DATA","question":"<exact question text>","candidates":["<candidate>"]}' | python3 scripts/verify_relation.py
   ```
   For author/reviewer questions, retain candidates only when `direct_relation_records` is nonempty, or when `linked_relation_records` is nonempty and the output is a metadata-resolved display name. Inspect the returned paths rather than relying on its heuristic score.
6. Deduplicate according to the question predicate and verify temporal/version wording. Return only values with direct support; do not fabricate unsupported answers.
7. Write completed answers. `answers` must map every question key to a list. Supply a numeric scalar or numeric per-key object in `tokens`:
   ```sh
   echo '{"questions_path":"/root/question.txt","output_path":"/root/answer.json","answers":{},"tokens":0}' | python3 scripts/write_answer.py
   ```
   Replace the empty mapping with runtime-derived answer lists before running this command. Then validate:
   ```sh
   echo '{"answer_path":"/root/answer.json","questions_path":"/root/question.txt"}' | python3 scripts/validate_answer.py
   ```

## Script interfaces

All scripts receive one JSON object on stdin and emit one JSON object on stdout; they use only the Python standard library.

- `discover_json.py`: input `{root, max_files?, max_paths?}`; inventories JSON files, root shapes, field paths, and scalar examples.
- `search_json.py`: input `{root, question_path? | questions? | queries?, max_hits_per_question?}`; returns lexical evidence with source file, JSON path, match terms, value, and parent-record preview.
- `verify_relation.py`: input `{root, question, candidates, max_records?}`; returns direct candidate/relation records and explicit-identity links. It is a provenance checker, not an answer generator.
- `write_answer.py`: input `{answers, output_path?, questions_path?, tokens?}`; validates list answers, exact question-key coverage when a question path is supplied, and numeric non-negative token values before atomically writing the artifact. Its default token value is numeric `0`.
- `validate_answer.py`: input `{answer_path, questions_path?}`; reports structural, key, list-shape, and token-format violations without deciding factual correctness.

## Failure handling

Unreadable JSON, ambiguous aliases, missing direct attribution, and conflicting evidence require further investigation, not guessing. Do not modify the question file or supplied data files. If the task specifies a missing-data convention, apply it only where supported; otherwise report the ambiguity to the execution agent rather than inventing a textual answer.
