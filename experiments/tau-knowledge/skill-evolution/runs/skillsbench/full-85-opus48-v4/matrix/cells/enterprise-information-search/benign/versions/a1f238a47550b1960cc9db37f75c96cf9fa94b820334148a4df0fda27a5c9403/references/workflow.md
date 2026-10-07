# Working checklist for enterprise-information-search

1. `cat /root/question.txt` and parse (key, text) pairs. Note entity, relation,
   time/version constraint, and expected output type per question.
2. `echo '{"path":"/root/DATA","sample":1,"max_depth":2}' | python3 scripts/inspect.py`
   to map the tree. Then inspect the metadata files in full depth to learn how
   employees / customers / teams and their ids/names/emails are represented.
3. Build identity resolution from metadata (id <-> name <-> email). Prefer
   stable ids; use names/roles/teams only to disambiguate.
4. For each question, run `scripts/search.py` with targeted regex patterns.
   Start from exact identifiers, then names/aliases. Use `record_depth` to pull
   the enclosing record so you can read the attributed action and timestamp.
5. Maintain a candidate -> evidence ledger: {source file, exact action, entity
   the action concerns, time/version}. Keep only candidates whose action matches
   the asked relation (author != attendee != mention != reviewer). Drop pure
   co-occurrence, membership, acknowledgement, or discussion of another entity.
6. Honor the asked time/version window. Detect timestamp precision/timezone
   before ordering events across sources.
7. Decide output shape/type: list always; numbers for counts/measurements;
   strings for ids/names; booleans for yes/no.
8. Write with `scripts/write_answer.py`, passing a dict keyed by every question
   key, each `{"answer": value, "tokens": "<estimate>"}`.
9. Validate: reload answer.json, confirm key set == questions, every answer is a
   list, every entry has a tokens string.

## Type reminders
- A single count of 7 -> `[7]` (number), not `["7"]`.
- A single id like `EMP0421` -> `["EMP0421"]` (string).
- A format illustration using `"xxx"` is a placeholder, not a type signal.

## Tokens
No real token counter exists here. Record a stringified estimate (e.g.
characters-read/4) or a maintained tally; `"0"` is acceptable as a last resort.
Never drop the `tokens` key.
