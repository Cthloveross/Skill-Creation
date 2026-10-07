# Usage

## 1. Inspect the task inputs
```
cat /root/local.rules
cat /root/suricata.yaml
sed -n '1,200p' /root/generate_training_pcaps.py
ls -la /root/pcaps 2>/dev/null || echo 'no pcaps yet'
```
The generator script defines how each pcap is built. Note which flows are the
true positive(s) and which negatives flip exactly one requirement (wrong method,
wrong path, missing/changed header, short blob, wrong-length sig, etc.). Those
negatives are your false-positive guards.

If `/root/pcaps/` is empty, generate them:
```
cd /root && python3 generate_training_pcaps.py
```

## 2. Build and write the rule
Fill the parameters from the current task instruction (do NOT copy values from
any example). Example invocation shape:
```
echo '{
  "params": {
    "method": "POST",
    "path": "/telemetry/v2/report",
    "path_exact": true,
    "header": "X-TLM-Mode: exfil",
    "body_fields": [
      {"prefix": "blob=", "charclass": "[A-Za-z0-9+/]", "min": 80},
      {"prefix": "sig=", "charclass": "[0-9a-fA-F]", "exact": 64}
    ],
    "sid": 1000001,
    "rev": 1
  },
  "write_to": "/root/local.rules"
}' | python3 /app/environment/skills/current/scripts/build_rule.py
```
`write_to` overwrites the file with just the signature. If the task requires
keeping pre-existing lines, pass `"keep_existing": true`. Replace the script path
with wherever the Skill is installed (see the task's skill_directory).

Resulting signature shape (illustrative structure only):
```
alert http any any -> any any (msg:"..."; flow:established,to_server; \
  http.method; content:"POST"; \
  http.uri; content:"/telemetry/v2/report"; startswith; endswith; \
  http.header; content:"X-TLM-Mode: exfil"; nocase; \
  http.request_body; content:"blob="; pcre:"/blob=[A-Za-z0-9+\/]{80,}/"; \
  content:"sig="; pcre:"/sig=[0-9a-fA-F]{64}(?![0-9a-fA-F])/"; \
  sid:1000001; rev:1;)
```

## 3. Syntax check and replay
Quick syntax/load test:
```
suricata -c /root/suricata.yaml -S /root/local.rules -T
```
Full replay and alert summary:
```
echo '{"target_sid": 1000001}' | \
  python3 /app/environment/skills/current/scripts/run_and_check.py
```
Interpret `results`: every positive pcap must show `target_fired: true`; every
negative pcap must show `target_fired: false`. `stderr_tail` surfaces rule-load
or parse errors.

## 4. Debug guidance
- Positive misses:
  * Header match failing -> ensure `nocase` and the exact `Name: value` spacing
    the pcap uses; try `content` without the space or use a looser form.
  * Body not inspected -> confirm `http.request_body` is set before body
    `content`/`pcre`; verify the request actually carries a body in the pcap.
  * URI exactness too strict -> if the positive has a query string, set
    `path_exact:false`.
- Negative false positives:
  * `sig` length: the negative lookahead `(?![0-9a-fA-F])` prevents 65+ hex;
    `{64}` prevents fewer. Keep both.
  * `blob` length: `{80,}` rejects shorter values.
  * Path substring: `startswith; endswith;` prevents prefix/suffix tricks.

Iterate build -> replay until positives all alert and negatives stay clean, then
leave the final `/root/local.rules` in place as the deliverable.
