#!/usr/bin/env python3
"""Locate the Erlang/OTP SSH connection handler and the dispatch clauses.

stdin JSON:  {"root": "<optional search root, default /app/workspace>"}
stdout JSON: {
  "root": str,
  "handler_files": [str, ...],         # candidate ssh_connection_handler.erl paths
  "primary": str|null,                  # best candidate
  "conn_msg_records": [str, ...],       # connection-protocol record names found
  "handle_event_lines": [int, ...],     # 1-based lines starting handle_event clauses
  "handle_msg_call_lines": [int, ...],  # lines calling ssh_connection:handle_msg
  "state_tuple_hits": [int, ...],       # lines mentioning {connected, ...}
  "notes": [str, ...]
}
The caller should read the reported line ranges with the terminal before editing.
"""
import json, os, re, sys

CONN_RECORDS = [
    "ssh_msg_global_request", "ssh_msg_request_success", "ssh_msg_request_failure",
    "ssh_msg_channel_open", "ssh_msg_channel_open_confirmation",
    "ssh_msg_channel_open_failure", "ssh_msg_channel_window_adjust",
    "ssh_msg_channel_data", "ssh_msg_channel_extended_data",
    "ssh_msg_channel_eof", "ssh_msg_channel_close",
    "ssh_msg_channel_request", "ssh_msg_channel_success", "ssh_msg_channel_failure",
]


def find_handler(root):
    hits = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f == "ssh_connection_handler.erl":
                hits.append(os.path.join(dirpath, f))
    hits.sort()
    return hits


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    root = data.get("root") or "/app/workspace"
    out = {
        "root": root, "handler_files": [], "primary": None,
        "conn_msg_records": [], "handle_event_lines": [],
        "handle_msg_call_lines": [], "state_tuple_hits": [], "notes": [],
    }
    if not os.path.isdir(root):
        out["notes"].append("root does not exist: %s" % root)
        print(json.dumps(out)); return
    handlers = find_handler(root)
    out["handler_files"] = handlers
    if not handlers:
        out["notes"].append("ssh_connection_handler.erl not found; search the tree manually.")
        print(json.dumps(out)); return
    primary = handlers[0]
    out["primary"] = primary
    try:
        with open(primary, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except Exception as e:
        out["notes"].append("could not read %s: %s" % (primary, e))
        print(json.dumps(out)); return
    found_records = set()
    he_re = re.compile(r"^\s*handle_event\s*\(")
    hm_re = re.compile(r"ssh_connection\s*:\s*handle_msg")
    st_re = re.compile(r"\{\s*connected\s*,")
    for i, line in enumerate(lines, 1):
        if he_re.search(line):
            out["handle_event_lines"].append(i)
        if hm_re.search(line):
            out["handle_msg_call_lines"].append(i)
        if st_re.search(line):
            out["state_tuple_hits"].append(i)
        for rec in CONN_RECORDS:
            if rec in line:
                found_records.add(rec)
    out["conn_msg_records"] = sorted(found_records)
    out["notes"].append(
        "Read handle_event clauses and handle_msg call sites; the dispatch of "
        "the connection-protocol records must be gated to {connected,_}.")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
