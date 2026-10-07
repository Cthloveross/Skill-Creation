---
name: http-form-exfil-suricata-rule
description: Create, install, and verify a Suricata HTTP rule when a request must satisfy an exact method, exact URI, required header field/value, and constrained form-style body fields. Use for custom HTTP exfiltration detections where all observations must occur in one request transaction.
---

# HTTP form exfiltration Suricata rule

## Inputs

Read the current task request and runtime files before building the rule. Extract:

- required `sid`, message, and revision;
- HTTP method and exact request-target/path;
- required header name and value;
- body parameter name, Base64-looking alphabet, and minimum value length;
- signature parameter name and exact hexadecimal length;
- destination rules file, Suricata configuration, and pcap locations.

Do not infer literals, pcap labels, expected alert counts, or configuration paths from this Skill. Use only the current public task inputs.

## Detection design

Use one `alert http` signature with `flow:established,to_server` so all conditions are conjunctive for the same parsed HTTP request. Select the intended sticky HTTP buffer immediately before each condition:

1. `http.method` for the method.
2. `http.uri` with an anchored PCRE for the exact URI. Anchoring prevents a matching prefix, a suffix, or an added query string from qualifying when the task says the path is exact.
3. `http.header` with a line-bounded PCRE. Header names are case-insensitive; keep the header value case-sensitive unless the public requirement says otherwise.
4. `http.request_body` for each form-field PCRE.

Treat body names as fields, not arbitrary substrings: require a start-of-body or form delimiter before the name and a form delimiter or end-of-body after the value. A Base64-looking field should use the standard Base64 alphabet (`A-Z`, `a-z`, `0-9`, `+`, `/`, and terminal padding) and a length check that includes padding. The signature field must have exactly the requested number of hex characters and a field boundary after it.

The packaged generator implements this structure without embedding task-specific literals. It uses `&` and `;` as form delimiters. If the public task specifies another serialization, do not claim this generator covers it; adapt the body-field grammar and validate it against the supplied traffic.

## Build and install

Create a JSON specification from the task values, using this schema:

```json
{
  "sid": "required positive integer",
  "message": "alert text",
  "method": "required HTTP method",
  "uri": "required exact URI",
  "header_name": "required header name",
  "header_value": "required header value",
  "blob_name": "required body field name",
  "min_blob_chars": "required positive integer",
  "sig_name": "required body field name",
  "sig_hex_chars": "required positive integer",
  "rev": "optional positive integer; defaults to 1",
  "rules_path": "optional existing local rules path"
}
```

Run the generator with the actual specification:

```text
python3 scripts/build_suricata_rule.py < rule-spec.json
```

It reads one JSON object on stdin and emits one JSON object on stdout. Its output contains `rule`, `changed`, and, when `rules_path` was supplied, writes the rule into that file. Installation is an upsert: active single-line rules using the specified SID are removed and exactly one generated rule is appended; unrelated rules and comments are retained. Review the emitted `rule` before continuing.

If file mutation is not desired, omit `rules_path`, take the returned `rule`, and install it through the execution agent's normal file-editing capability. Do not add a second rule using the same SID.

## Static and engine validation

First validate that the target SID is present exactly once:

```text
python3 scripts/validate_local_rules.py < validation-spec.json
```

`validation-spec.json` must contain `rules_path` and `sid`. The script emits JSON with `ok`, `target_rule_count`, and `errors`; it exits nonzero on malformed input or a failed check. This is structural validation only, not a replacement for Suricata parsing.

Then syntax-check the installed rules with the supplied configuration and replay every supplied pcap offline using separate output directories. Use the execution environment's Suricata binary and its normal offline pcap mode; do not assume a binary, config path, or output format that was not supplied. Inspect the resulting structured alert log for the required SID.

When the pcap generator or public task identifies positive and negative cases, confirm all of the following:

- every true positive request produces the required SID;
- no negative request produces that SID;
- negative cases that change only method, URI, header, blob length/alphabet, signature length/alphabet, or form-field boundaries do not match;
- an alert represents one request satisfying every condition, rather than observations from different transactions.

## Failure handling

Stop and report rather than weakening the rule if a required literal, pcap, configuration file, or Suricata executable is missing. A parser failure means the rule syntax or configured feature set must be corrected. A false positive usually means an unanchored URI, unbounded header/value, or body substring match; a false negative usually means the wrong HTTP buffer, request-body inspection limits, unsupported body serialization, or a requirement not represented in the field grammar. Preserve the required SID while correcting the underlying condition.
