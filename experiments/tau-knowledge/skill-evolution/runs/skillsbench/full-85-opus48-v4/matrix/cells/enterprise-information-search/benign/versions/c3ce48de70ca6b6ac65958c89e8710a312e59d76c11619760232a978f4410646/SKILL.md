---
name: enterprise-information-search
description: >-
  Answer a set of enterprise-data retrieval questions over a directory of JSON
  exports (per-product activity logs plus metadata about employees, customers,
  and teams) and write a correctly shaped answer.json. Use this Skill whenever a
  task supplies /root/question.txt with keyed questions (q1, q2, ...) and a
  /root/DATA tree of JSON files, and asks for answers written to a dict file
  where each value is {"answer": [...], "tokens": "..."}. The Skill provides
  schema inspection, cross-file search, targeted retrieval helpers, and an
  answer-writer that enforces the output contract. Products, field names,
  identifiers, employee-ids, URLs, and answer mappings are all discovered from
  the supplied files at runtime; none are hardcoded.
---

# Enterprise Information Search

## When to use

The public task gives you:
- `/root/question.txt` — plain text listing the questions, keyed `q1`, `q2`,...
  Read it first and parse out each question key and its full text.
- `/root/DATA/` — a tree of JSON files: a `metadata/` folder (employee,
  customers, salesforce_team records) and a `products/` folder with one large
  JSON file per product (activity / interaction logs). Confirm the layout with
  `scripts/inspect.py`; do not assume file names or fields blindly.

You must write `/root/answer.json` as a Python-readable dict:
```
{"q1": {"answer": [...], "tokens": "..."}, "q2": {"answer": [...], "tokens": "..."}}
```
Rules enforced by this Skill:
- Every `answer` value is a **list**, even for a single item (length-1 list).
- Each question carries a `tokens` field (string). There is no real token
  counter here; `"0"` or a stringified estimate is acceptable. Never omit it.
- Preserve JSON semantic types inside the list: employee-ids and URLs are
  **strings**; counts/measurements are **numbers**; a `"xxx"` in the prompt's
  format illustration is a placeholder, not a type signal.

## Observed corpus schema (verify with inspect.py before relying on it)

Each `DATA/products/<Product>.json` is a dict with arrays:
- `documents[]`: `{content, date, author, document_link, feedback?, type, id}`.
  `author` is an **employee-id** (e.g. `eid_...`). Multiple version rows
  (draft/final/latest) share the same `type` (e.g. "Market Research Report").
- `meeting_transcripts[]`: `{transcript, date, document_type, participants, id}`.
  `participants` is a list of employee-ids. The transcript text starts with an
  "Attendees" line of NAMES that correspond **positionally** to `participants`.
  The facilitator who asks "I wanted to get your feedback ..." is usually the
  document **author** and is NOT in participants/attendees. Everyone listed in
  `participants` of a document-review transcript is a **reviewer** of that
  document (they each give feedback in the transcript body).
- `slack[]`: `{Channel, Message:{User:{userId, timestamp, text}}, ThreadReplies[], id}`.
  `userId` is an employee-id.
- `urls[]`: `{link, description, id}`.
- `prs[]`: `{..., user:{login}, reviews[], ...}` where `login` is an employee-id.

`DATA/metadata/employee.json` maps `eid_*` -> `{name, role, location, org}`.
`salesforce_team.json` is the org tree. **Caution: display names are heavily
duplicated** (many "Charlie Davis", "Julia Smith", ...). Do NOT resolve a
transcript name to an eid by searching employee.json by name — it is ambiguous.
Use the positional `participants`<->attendees mapping and the `author`/`userId`/
`login` id fields directly. Answer with employee-ids, not names, when the
question asks for employee IDs.

## Quick start (do this first)

This Skill is self-contained. The single authoritative step is to run the
end-to-end entrypoint, which reads `/root/question.txt` and `/root/DATA`,
derives every answer from the data (nothing hardcoded), and writes
`/root/answer.json` in the required contract. Run it from the Skill directory
(or by absolute path; it is cwd-independent and never reads stdin):

```
python3 scripts/run.py
# or, equivalently, from anywhere:
python3 "$SKILL_DIR/scripts/run.py"
```

`run.py` prints a per-question report (`intent`, `product`, `doc_type`,
`answer`). Treat the written `/root/answer.json` as the task answer; do not
overwrite it with ad-hoc reasoning. Only intervene when the report flags a
question:
- `intent == "unsupported"`, or `product`/`doc_type` is null → that question's
  phrasing was not recognized. Handle it manually with `scripts/inspect.py`,
  `scripts/search.py`, and the `scripts/retrieve.py` ops documented below, then
  patch just that key and rewrite with `scripts/write_answer.py`.

Supported question intents (classified from the question text):
- authors and/or key reviewers of a named document type for a product
  (words "author"/"review" + a `documents[].type` phrase such as
  "Market Research Report"). Answer = the document author(s) **plus** the
  reviewers = participants (employee-ids) of that document's review meeting
  (`meeting_transcripts` whose `document_type` matches). Include authors only if
  "author" is asked and reviewers only if "review" is asked.
- demo URLs for a product's **competitor** products ("demo" + "url"/"link" +
  "competitor"). Answer = external (off the org-internal slack host) demo URLs
  shared in slack. The org's own product demos (on the internal host) are
  excluded.
- team members who gave insights on competitors' strengths/weaknesses
  ("competitor" + "insight"/"strength"/"weakness"). Answer = employee-ids who
  authored a competitor-analysis message; pure acknowledgers are excluded.

Finish by validating as in "Validation before finishing".

## Method

1. **Read the questions.** `cat /root/question.txt`; split into (key, text).
   For each, note the entity (which product), the relation asked (author /
   reviewer / insight-provider / demo-sharer / count / ...), any constraint, and
   the required output type.

2. **Inventory the data.** `scripts/inspect.py` to confirm the tree and
   per-file structure before searching.

3. **Use targeted retrieval helpers** in `scripts/retrieve.py` (stdin JSON ->
   stdout JSON). They implement the semantic conventions above so results are
   reproducible. Pick the right product file from the question's product name
   (match it to a file in `DATA/products/`, including aliases found in the data,
   e.g. a product may be referenced by a codename inside its own file).

   - **Authors & reviewers of a document type** (e.g. "authors and key reviewers
     of the Market Research Report for <Product>"):
     ```
     echo '{"op":"authors_reviewers","product_file":"/root/DATA/products/<Product>.json",
            "doc_type":"Market Research Report"}' | python3 scripts/retrieve.py
     ```
     Combine `authors` + `reviewers` (both are employee-ids) when the question
     asks for "authors and reviewers". Use only `authors` or only `reviewers`
     when the question asks for just one role.

   - **Competitor demo URLs shared by team members** (e.g. "demo URLs shared by
     team members for <Product>'s competitor products"):
     ```
     echo '{"op":"competitor_demos","product_file":".../<Product>.json"}' | python3 scripts/retrieve.py
     ```
     Answer with `external_shared_demos[].url` (the demos of **competitor**
     products, hosted off the internal slack host). Exclude the org's own
     product demos, which are on the internal host (default `sf-internal`;
     override via `"internal_host"`). `external_demo_urls` corroborates the set.

   - **Team members who gave insights on competitors' strengths/weaknesses**:
     ```
     echo '{"op":"competitor_insights","product_file":".../<Product>.json"}' | python3 scripts/retrieve.py
     ```
     Answer with `insight_providers` (employee-ids who authored a competitor-
     analysis message). People who only reply "Thanks for the insights ..." are
     NOT providers and are excluded.

4. **Verify the semantic role** of each candidate against the question before
   accepting it (author != attendee != acknowledger != reviewer; a competitor
   demo != the org's own demo). Use `scripts/search.py` for anything the helpers
   do not cover, keeping provenance (file, pointer, enclosing record).

5. **Decide shape/type.** Lists for collections; length-1 list for a single
   item; numbers for counts; strings for ids/URLs/names.

6. **Write the output** with `scripts/write_answer.py`, passing a dict keyed by
   every question key, each `{"answer": <value>, "tokens": "<estimate>"}`. Then
   re-read `/root/answer.json` to confirm it parses and the key set equals the
   questions.

## End-to-end example (illustrative; derive real values from the data)

```
# q: authors and key reviewers of the Market Research Report for <Product>
A=$(echo '{"op":"authors_reviewers","product_file":"/root/DATA/products/<Product>.json","doc_type":"Market Research Report"}' | python3 scripts/retrieve.py)
# q: demo URLs shared for <Product2>'s competitor products
D=$(echo '{"op":"competitor_demos","product_file":"/root/DATA/products/<Product2>.json"}' | python3 scripts/retrieve.py)
# q: team members who gave insights on <Product2> competitors' strengths/weaknesses
I=$(echo '{"op":"competitor_insights","product_file":"/root/DATA/products/<Product2>.json"}' | python3 scripts/retrieve.py)
# assemble q->{"answer":[...],"tokens":"0"} from authors+reviewers / external_shared_demos urls / insight_providers,
# then pipe to scripts/write_answer.py.
```

## Scripts

All scripts read one JSON object from **stdin** and print one JSON object to
**stdout** (Python 3 standard library only).

### scripts/run.py
End-to-end entrypoint. Reads question.txt + DATA, writes answer.json, prints a
report. Input (optional, via stdin): `{"question_file":..,"data_dir":..,"out":..,
"tokens":".."}`; defaults are the /root paths. Output: `{"written":..,"keys":[..],
"report":[{"key","question","intent","product","doc_type?","answer"}...]}`.

### scripts/inspect.py
Summarize JSON structure without dumping whole files.
- Input: `{"path": "/root/DATA", "sample": 2, "max_depth": 3}` (file or dir).
- Output: `{"root":..., "items":[{"file":..,"bytes":..,"summary":{...}}]}`.

### scripts/search.py
Regex search over string values with provenance.
- Input: `{"paths":[...] | "dir":"/root/DATA", "patterns":["..."], "ignore_case":true,
   "max_matches":50, "record_depth":1, "require_all":false}`.
- Output: `{"count":N, "matches":[{"file":..,"pointer":"/a/0/b","value":..,"record":{...}}]}`.

### scripts/retrieve.py
Targeted retrieval helpers (ops `authors_reviewers`, `competitor_demos`,
`competitor_insights`) implementing the corpus conventions above. See the
module docstring for exact input/output schemas. Nothing is hardcoded; every
value is read from the supplied product file.

### scripts/write_answer.py
Write the final answer file enforcing the contract.
- Input: `{"path":"/root/answer.json","default_tokens":"0","answers":{"q1":{"answer":...,"tokens":...}, ...}}`.
  Each `answer` is wrapped in a list if not already one; `None`->`[]`; `tokens`
  is stringified (uses `default_tokens` if missing).
- Output: `{"path":..,"keys":[...],"written":true}` and the file is written.

## Validation before finishing
- `python3 -c "import json;d=json.load(open('/root/answer.json'));print(sorted(d))"`.
- Confirm the key set equals the questions parsed from question.txt.
- Every `answer` is a list; every entry has a `tokens` string.
- Spot-check each item against its asked semantic role (author/reviewer/
  insight-provider/competitor-demo) and that ids are ids and URLs are URLs.

## Failure modes handled
- Missing/renamed files: `inspect.py` enumerates whatever exists; never hardcode.
- Ambiguous display names: resolve via id fields and positional participant
  mapping, not by name lookup.
- Over-inclusive answers: exclude co-occurrence, attendance of unrelated
  meetings, acknowledgements, and the org's own demos when competitors are asked.
- Unsupported question: fall back to `search.py`, record evidence, and answer
  with the best-supported ids/values; still emit valid JSON with the tokens key.
