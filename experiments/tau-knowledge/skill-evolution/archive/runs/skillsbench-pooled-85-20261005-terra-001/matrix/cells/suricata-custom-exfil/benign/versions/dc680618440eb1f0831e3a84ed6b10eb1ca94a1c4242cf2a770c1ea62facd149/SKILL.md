---
name: http-form-exfil-suricata-rule
description: Create, install, and verify a Suricata HTTP rule when one request must satisfy an exact method, exact URI, required header field/value, and two constrained form-style body fields. Use for custom HTTP exfiltration detections requiring all observations in the same HTTP transaction.
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

Do not infer literals, pcap labels, expected alert counts, or configuration paths from this Skill. Use only current public task inputs.

## Detection design

Use one `alert http` signature with `flow:established,to_server`. Conditions in the signature are conjunctive for the same parsed request. Select each intended sticky HTTP buffer once:

1. `http.method` followed by a method condition.
2. `http.uri` followed by an anchored PCRE for the exact URI. This rejects prefixes, suffixes, and query strings when an exact path is required.
3. `http.header` followed by a line-bounded PCRE. Header names are case-insensitive; leave the header value case-sensitive unless the task says otherwise.
4. **One** `http.request_body` buffer followed by **one combined PCRE** containing positive lookaheads for both required form fields.

Suricata rejects duplicate sticky-buffer instances in a rule. Do not select `http.request_body` separately for each field. The combined body PCRE checks both fields independently, so their order may vary while both must exist in the same request body.

Treat form names as fields rather than substrings: require start-of-body or a form delimiter before each name and a form delimiter or end-of-body after each value. The packaged generator supports `&` and `;` delimiters. Its Base64-looking grammar permits the standard Base64 alphabet and only terminal padding; its minimum-length test includes padding. The hexadecimal field has both an exact character count and a trailing field boundary.

If a task specifies another serialization, body encoding, or delimiter grammar, do not claim this generator covers it. Adapt the combined body grammar and validate it against the supplied traffic.

## Build and install

Create a JSON specification from task values:

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

Run:

```text
python3 scripts/build_suricata_rule.py < rule-spec.json
```

The script reads one JSON object on stdin and emits one JSON object on stdout:

```json
{"ok": true, "rule": "...", "changed": true, "rules_path": "/path/to/rules"}
```

On invalid input or write failure it emits `{"ok": false, "error": "..."}` and exits nonzero. When `rules_path` is supplied, installation is an upsert: active single-line rules using the requested SID are removed and one generated rule is appended. Unrelated rules and comments are retained. Review the returned rule before continuing.

If file mutation is not desired, omit `rules_path`, take the returned `rule`, and install it through the execution agent's normal file-editing capability. Do not add a second rule using the same SID.

## Validate

First perform structural validation:

```text
python3 scripts/validate_local_rules.py < validation-spec.json
```

Input schema is:

```json
{"rules_path": "/path/to/local.rules", "sid": 1}
```

The script emits `ok`, `target_rule_count`, and `errors`; it exits nonzero for malformed input or a failed structural check. This does not replace Suricata parsing.

Then syntax-check the installed rule with the supplied configuration and replay every supplied pcap offline. Provide a writable log directory when invoking Suricata, since task configurations can otherwise select an unwritable default log location. Inspect structured alert logs for the required SID.

For supplied positive and negative traffic, verify:

- every complete exfiltration request alerts with the required SID;
- no negative request alerts with that SID;
- method, URI, header, blob alphabet/length, signature alphabet/length, and field-name/boundary negatives do not match;
- overlong signature values do not match merely because they begin with the required number of hex characters;
- the two body fields may appear in either order but must occur in the same request body.

## Failure handling

Stop and report rather than weakening the rule if a required literal, pcap, configuration file, or Suricata executable is missing. A parser error can indicate duplicate sticky buffers or unsupported syntax; retain all required conditions while expressing multiple body tests in one body-buffer PCRE. A false positive generally indicates an unanchored URI, unbounded header/value, or unbounded form field. A false negative can indicate the wrong HTTP buffer, request-body limits, or unsupported serialization. Preserve the required SID while correcting the underlying condition.
