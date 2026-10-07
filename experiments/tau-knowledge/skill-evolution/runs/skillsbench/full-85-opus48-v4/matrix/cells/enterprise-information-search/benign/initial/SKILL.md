---
name: enterprise-information-search
description: >-
  Answer a set of enterprise-data retrieval questions over a directory of JSON
  exports (product activity logs plus metadata about employees, customers, and
  teams) and write a correctly shaped answer.json. Use this Skill whenever a
  task supplies /root/question.txt with keyed questions (q1, q2, ...) and a
  /root/DATA tree of JSON files, and asks for answers written to a dict file
  where each value is {"answer": [...], "tokens": "..."}. The Skill provides
  schema-inspection, cross-file search, and an answer-writer that enforces the
  required output contract. All products, field names, identifiers, and answer
  mappings are discovered from the supplied files at runtime; nothing is
  hardcoded.
---

# Enterprise Information Search

## When to use

The public task gives you:
- `/root/question.txt` — plain text listing the questions, usually keyed `q1`,
  `q2`, ... Read it first and parse out each question key and its full text.
- `/root/DATA/` — a tree of JSON files. In the observed layout there is a
  `metadata/` subfolder (e.g. employee, customers, salesforce_team records) and
  a `products/` subfolder with one large JSON file per product (activity /
  interaction logs). **Do not assume these exact names or fields** — enumerate
  the directory and inspect structures at runtime.

You must write `/root/answer.json` as a Python-readable dict:
```
{"q1": {"answer": [...], "tokens": "..."}, "q2": {"answer": [...], "tokens": "..."}}
```
Rules from the opening prompt that this Skill enforces/helps with:
- Every answer value is stored in a **list**, even a single item (length-1 list).
- Each question also carries a `tokens` field (string) logging consumed tokens.
- Preserve JSON **semantic types** inside the list: counts/measurements as
  numbers, identifiers/names as strings, booleans as booleans. A one-item
  numeric answer is `[123]`, not `["123"]`, unless the value is truly an id/label.

## Method

1. **Read the questions.** `cat /root/question.txt`. Split into (key, text).
   Keys are typically `qN`. If a line has no `qN:` prefix, infer keys in order.
   For each question, note: the entity (person/product/customer/team), the
   relation asked (authored / reviewed / attended / mentioned / contributed /
   count / list), any time or version constraint, and the required output type
   (single id, list of names, a number, a boolean).

2. **Inventory the data.** `python3 scripts/inspect.py` with a path to list the
   DATA tree and summarize each file's structure (top-level container, keys,
   value types, a small sample). Learn how people are represented (internal id
   vs. display name vs. email-like address) and how products/customers/teams
   link together **before** searching. Build identity resolution from the
   metadata files (employee / team / customer records), using stable ids where
   present and names only as disambiguating evidence.

3. **Search programmatically, not by eyeballing whole files.** Use
   `scripts/search.py` to find records whose string values match query patterns
   (regex, case-insensitive by default). It returns, for each hit, the file, a
   JSON-pointer path, and the nearest enclosing record so you keep provenance.
   Narrow with exact identifiers first, then names/aliases/normalized text.
   Follow cross-references only when they add evidence for the asked relation.

4. **Verify the semantic role before accepting a candidate.** Keep a candidate
   -> evidence ledger: source file, the exact attributed action, which entity it
   concerns, and the time/version context. Apply the question's predicate to
   every candidate. Exclude candidates supported only by co-occurrence, team
   membership, attendance, acknowledgement, or discussion of a *different*
   entity. Deduplicate only after recording evidence. Respect any time/version
   window stated by the question; detect timezone/precision before ordering.

5. **Decide the shape and type of each answer.** Lists for collections; a
   length-1 list for a single item. Numbers for counts/measurements; strings for
   ids/names. Do not let a placeholder like `"xxx"` in the format illustration
   turn a numeric measurement into a string.

6. **Write the output.** Build a Python dict mapping each question key to
   `{"answer": <value>, "tokens": <string>}` and pass it to
   `scripts/write_answer.py`, which normalizes every `answer` into a list,
   coerces `tokens` to a string, validates JSON types, and writes
   `/root/answer.json`. Then re-read the file to confirm it parses and contains
   exactly the question keys from question.txt.

## Tokens field

The prompt asks to log consumed tokens per question. There is no oracle token
counter in this environment, so record a defensible estimate as a **string**
(e.g. derived from characters read / 4, or a running tally you maintain). The
writer accepts any value and stringifies it; a numeric-looking string such as
`"0"` is acceptable when no better figure exists. The grading focus is the
`answer` content and its shape — never omit the `tokens` key.

## Scripts

All scripts read a single JSON object from **stdin** and print one JSON object to
**stdout**. Run them with the task's Python 3 (standard library only).

### scripts/inspect.py
Summarize JSON structure without dumping whole files.
- Input: `{"path": "/root/DATA", "sample": 2, "max_depth": 3}`.
  - If `path` is a directory, lists files recursively and summarizes each
    (bytes + top-level structure). If a file, summarizes just that file.
- Output: `{"root": path, "items": [{"file":..., "bytes":..., "summary": {...}}]}`
  where `summary` describes container type, keys with value-type tags, length of
  arrays, and a trimmed sample.
- Example:
  `echo '{"path":"/root/DATA/metadata/employee.json","sample":1}' | python3 scripts/inspect.py`

### scripts/search.py
Regex search over string values inside one or more JSON files, with provenance.
- Input: `{"paths": ["/root/DATA/products/LeadForce.json"], "patterns": ["review"],
   "ignore_case": true, "max_matches": 50, "record_depth": 1}`.
  - `paths` may be files or directories (directories are walked for `*.json`).
    Alternatively give `"dir": "/root/DATA"`.
  - `patterns` is a list of regexes; a record matches if ANY pattern matches a
    string value (set `"require_all": true` to need all). `record_depth`
    controls how far up the tree the returned enclosing record is taken.
- Output: `{"count": N, "matches": [{"file":..., "pointer":"/a/0/b",
   "value":"...matched string...", "record": {...nearest record...}}]}`
  (truncated at `max_matches`).
- Example:
  `echo '{"dir":"/root/DATA/products","patterns":["ProductX","demo"],"ignore_case":true,"max_matches":20}' | python3 scripts/search.py`

### scripts/write_answer.py
Write the final answer file enforcing the output contract.
- Input: `{"path": "/root/answer.json", "default_tokens": "0",
   "answers": {"q1": {"answer": "Alice", "tokens": 1234},
               "q2": {"answer": [1,2,3]}}}`.
  - Each entry's `answer` is wrapped in a list if it is not already a list
    (strings and numbers become length-1 lists; existing lists are kept). `None`
    becomes `[]`. `tokens` is coerced to a string; if missing, `default_tokens`
    is used.
  - You may pass answers as a bare value instead of a dict, e.g.
    `{"q1": "Alice"}`; it is treated as `{"answer": "Alice"}`.
- Output: `{"path":..., "keys":[...], "written": true}` and the file is written
  as pretty JSON.
- Example:
  `echo '{"path":"/root/answer.json","answers":{"q1":{"answer":"Alice","tokens":"100"}}}' | python3 scripts/write_answer.py`

## Validation before finishing
- `python3 -c "import json;d=json.load(open('/root/answer.json'));print(sorted(d))"`
  confirms it parses and lists keys.
- Confirm the key set equals the questions parsed from question.txt.
- Spot-check that every `answer` is a list and every entry has a `tokens` string.
- Re-read your evidence ledger and confirm each listed item truly satisfies the
  asked relation and time/version constraint.

## Failure modes handled
- Missing/renamed files: inspect enumerates whatever exists; never hardcode names.
- Huge files: scripts stream per-file with json.load (files are ~1MB) and cap
  returned matches; search returns pointers so you fetch detail selectively.
- Over-inclusive answers: the ledger + predicate guard against co-occurrence.
- Wrong JSON types/shapes: write_answer enforces list wrapping and string tokens
  but preserves inner numeric/string types you supply.
