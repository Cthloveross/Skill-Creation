---
name: suricata-http-exfil-rule
description: >
  Author and validate a Suricata signature that alerts (with a required sid)
  on a custom HTTP data-exfiltration pattern. Use when a task supplies pcaps, a
  suricata.yaml, and a local.rules file and asks you to detect an HTTP POST whose
  path, a specific header, and request-body fields all match given constraints,
  while avoiding false positives. The method builds an HTTP-aware rule using
  sticky buffers (http.method, http.uri, http.header, http.request_body) with
  conjunctive conditions on one transaction, then syntax-checks and replays it
  against the positive/negative pcaps and confirms the signature id in eve.json.
---

# Suricata HTTP exfil detection rule

## When to use
The public task gives you an opening instruction that enumerates the exfil
conditions (an HTTP method, an exact request path, a required request header, and
request-body field constraints), a `sid` to emit, pcaps under `/root/pcaps/`, a
config at `/root/suricata.yaml`, and a rules file at `/root/local.rules` to
update. Read those files first; the concrete literals, lengths, and sid come from
the current task's instruction and runtime files, not from this document.

## Method (why these choices)
HTTP is parsed and reassembled by Suricata, so inspect semantic buffers rather
than raw packet bytes. Place each requirement in the buffer that represents it,
and keep them in ONE signature so the conditions are conjunctive over the same
transaction:

- Method -> `http.method` + `content:"POST";` (match the exact method token).
- Exact path -> `http.uri` + `content` anchored with `startswith; endswith;` so a
  substring or prefix (e.g. `/telemetry/v2/report-extra` or a query string) does
  not falsely match. If the task intends "path only, query allowed", relax by
  using `startswith;` and a `pcre` anchored at `^`; prefer exactness unless the
  negative pcaps show otherwise.
- Required header -> `http.header` + `content:"<Name>: <value>"; nocase;`
  because header names are case-insensitive.
- Body fields -> `http.request_body` with a `content` prefilter plus a `pcre`
  that encodes the character class, length, and length-exactness:
  * A "Base64-looking value of at least N chars" -> `[A-Za-z0-9+/]{N,}`.
  * "Exactly K hex chars" -> `[0-9a-fA-F]{K}` followed by a negative lookahead
    `(?![0-9a-fA-F])` (and the `{K}` quantifier) so K+1 or more does NOT match
    while fewer than K also fails. Distinguish "at least" from "exactly".

Use the exact `sid` the task requires and add `rev:1;`. Pick literal vs regex per
requirement: literals for fixed tokens, regex for length/charset constraints.

## Steps
1. Read `/root/local.rules`, `/root/suricata.yaml`, and
   `/root/generate_training_pcaps.py`. The generator reveals which pcaps are
   positive (true exfil) and which are negative (each flips one requirement); use
   this labeling to judge correctness, not filenames alone.
2. If `/root/pcaps/` is empty or missing, run the generator
   (`python3 /root/generate_training_pcaps.py`) to produce the pcaps.
3. Build the rule with `scripts/build_rule.py` (fill its JSON parameters from the
   task instruction) or hand-write it following the method above. Write it into
   `/root/local.rules`. Keep any pre-existing required lines; append/replace the
   detection signature carrying the required sid.
4. Validate with `scripts/run_and_check.py`: it runs Suricata offline against each
   pcap and parses `eve.json`, reporting which sids fired per pcap. Confirm the
   required sid fires on every positive pcap and on no negative pcap. If a
   positive misses, loosen anchoring/normalization or check body inspection; if a
   negative fires, tighten the condition that pcap was designed to flip.
5. Iterate until positives all alert and negatives are all clean, then leave the
   final signature in `/root/local.rules`.

## Deliverable
`/root/local.rules` must contain exactly one working signature that emits the
required sid for true exfil traffic and nothing for the negatives. This is the
graded artifact; produce it with the executor, do not merely describe it.

## Scripts
- `scripts/build_rule.py` (stdin JSON -> stdout JSON): constructs the signature
  string from parameters and optionally writes it to a target file.
- `scripts/run_and_check.py` (stdin JSON -> stdout JSON): replays pcaps through
  Suricata and summarizes alerts per pcap by sid.
- `scripts/rule_lib.py`: shared builder used by both.

See `references/usage.md` for exact invocation examples and parameter schemas.
