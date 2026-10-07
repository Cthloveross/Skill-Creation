---
name: suricata-http-conjunctive-exfil-rule
description: Create and validate a Suricata HTTP rule when an alert must require an exact method, exact request path, a semantic header, and independently bounded fields in an HTTP request body. Use for updating a supplied local.rules file and testing it against supplied PCAPs.
---

# Suricata HTTP conjunctive detection rule

Use parsed HTTP buffers rather than packet-byte offsets. Keep all conditions in one `alert http` signature so they apply conjunctively to a single HTTP transaction.

## Inputs

Obtain these values from the current task, not from this Skill:

- destination rules file and Suricata configuration;
- SID and message;
- exact HTTP method and path;
- required header name and exact header value;
- body parameter names, the minimum Base64-looking length, and exact hexadecimal length;
- PCAP directory, if replay validation is requested.

The packaged generator accepts one JSON object on stdin:

```json
{
  "sid": 1000001,
  "message": "HTTP telemetry exfiltration",
  "method": "POST",
  "path": "/telemetry/v2/report",
  "header_name": "X-TLM-Mode",
  "header_value": "exfil",
  "blob_parameter": "blob",
  "minimum_blob_chars": 80,
  "signature_parameter": "sig",
  "signature_hex_chars": 64,
  "output_path": "/root/local.rules",
  "write_mode": "append_if_absent"
}
```

`output_path` and `write_mode` are optional. Without `output_path`, the script only returns the generated rule in JSON. `write_mode` is either `append_if_absent` (the default) or `replace`.

## Procedure

1. Inspect the supplied rules file and configuration first. Preserve unrelated local rules. Confirm that the configuration loads the intended rules file and that HTTP inspection/request-body limits are sufficient for the required fields.
2. Generate the rule by passing the task values as JSON to:

   ```sh
   python3 /app/environment/skills/current/scripts/build_http_exfil_rule.py
   ```

   When writing directly to the task rules file, include `output_path` and normally use `append_if_absent`. If that SID is already present but its rule is incorrect, deliberately replace or edit that one rule rather than blindly appending a duplicate SID.
3. The generated signature uses:
   - `http.method` plus an anchored PCRE for the exact method;
   - `http.uri` plus an anchored PCRE for the exact URI/path;
   - `http.header` with a case-insensitive header-name match, flexible legal horizontal whitespace around the colon, and an exact case-sensitive value;
   - `http.request_body` with separate bounded form-field PCREs. Each requires a field boundary, so a matching prefix, suffix, or similarly named field does not qualify.
4. Syntax-check the actual deployed setup before replaying traffic, for example:

   ```sh
   suricata -T -c /root/suricata.yaml
   ```

   Use the task's actual configuration and rule paths if different. A failed syntax check, an unloaded local rules file, or an unavailable Suricata binary is a prerequisite failure; do not claim that the rule was validated.
5. Replay each supplied PCAP using the supplied configuration into a fresh log directory. Inspect structured alert events (normally `eve.json`) and confirm that every expected positive alert has the requested SID. Examine negative traffic that changes method, path, header, blob field, blob length/characters, signature field, or signature length/characters; it must not produce that SID.

## Interpretation and limitations

The body expressions intentionally model URL-form-style fields delimited by `&` or body boundaries. If the public requirement instead specifies JSON, multipart, repeated parameters, percent-encoded values, or another serialization, do not apply this rule unchanged: design field boundaries for that explicit representation and validate against it.

A Base64-looking value permits Base64 alphabet characters followed only by optional terminal padding. The field must contain at least the configured number of alphabet characters. The signature field must contain exactly the configured number of hexadecimal characters and end at a field boundary.

The script emits JSON on stdout with `rule`, `written`, and (when applicable) `output_path`. Treat `written: false` under `append_if_absent` as a signal to inspect the existing SID rule; it is not proof that the existing rule is correct.
