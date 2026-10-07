#!/usr/bin/env python3
"""Heuristic verification of the SSH state-machine hardening patch.

stdin JSON:  {"file": "<path to edited ssh_connection_handler.erl>",
              "root": "<optional; used only to auto-find file if omitted>"}
stdout JSON: {
  "file": str|null,
  "checks": {
     "file_exists": bool,
     "has_connected_guard": bool,       # {connected,_} appears near conn-msg dispatch
     "has_disconnect_path": bool,        # a disconnect/reject appears for pre-auth
     "conn_records_present": bool,       # connection-protocol records referenced
     "paren_balanced": bool,
     "brace_balanced": bool,
     "erlc_available": bool,
     "erlc_syntax_ok": bool|null
  },
  "warnings": [str, ...],
  "advice": [str, ...]
}
These are advisory signals derived from the public requirement, not a grader.
"""
import json, os, re, subprocess, sys, shutil, tempfile

CONN_RECORDS = [
    "ssh_msg_global_request", "ssh_msg_channel_open", "ssh_msg_channel_request",
    "ssh_msg_channel_data", "ssh_msg_channel_eof", "ssh_msg_channel_close",
    "ssh_msg_channel_success", "ssh_msg_channel_failure",
]


def find_file(root):
    for dp, _d, fs in os.walk(root):
        if "ssh_connection_handler.erl" in fs:
            return os.path.join(dp, "ssh_connection_handler.erl")
    return None


def balanced(text, open_c, close_c):
    # crude: ignore chars inside %-comments and simple strings
    depth = 0
    in_str = False
    i = 0
    out = []
    for raw in text.splitlines():
        line = raw.split("%", 1)[0] if "%" in raw else raw
        out.append(line)
    clean = "\n".join(out)
    for ch in clean:
        if ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch == open_c:
                depth += 1
            elif ch == close_c:
                depth -= 1
                if depth < 0:
                    return False
    return depth == 0


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    path = data.get("file")
    root = data.get("root") or "/app/workspace"
    if not path:
        path = find_file(root)
    res = {
        "file": path,
        "checks": {
            "file_exists": False, "has_connected_guard": False,
            "has_disconnect_path": False, "conn_records_present": False,
            "paren_balanced": False, "brace_balanced": False,
            "erlc_available": False, "erlc_syntax_ok": None,
        },
        "warnings": [], "advice": [],
    }
    if not path or not os.path.isfile(path):
        res["warnings"].append("handler file not found; pass {\"file\": path}.")
        print(json.dumps(res)); return
    res["checks"]["file_exists"] = True
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    res["checks"]["has_connected_guard"] = bool(re.search(r"\{\s*connected\s*,", text))
    res["checks"]["has_disconnect_path"] = bool(
        re.search(r"disconnect|DISCONNECT|PROTOCOL_ERROR", text))
    res["checks"]["conn_records_present"] = any(r in text for r in CONN_RECORDS)
    res["checks"]["paren_balanced"] = balanced(text, "(", ")")
    res["checks"]["brace_balanced"] = balanced(text, "{", "}")

    erlc = shutil.which("erlc")
    res["checks"]["erlc_available"] = bool(erlc)
    if erlc:
        tmp = tempfile.mkdtemp()
        try:
            # syntax-only; a single module may not resolve all includes, so
            # treat only clear syntax errors as failure.
            p = subprocess.run(
                [erlc, "-o", tmp, path],
                capture_output=True, text=True, timeout=120)
            err = (p.stderr or "") + (p.stdout or "")
            syntax_bad = bool(re.search(r"syntax error|before:|illegal", err))
            res["checks"]["erlc_syntax_ok"] = (not syntax_bad)
            if err.strip():
                res["warnings"].append("erlc output (may include missing-include noise): "
                                        + err.strip()[:800])
        except Exception as e:
            res["warnings"].append("erlc run failed: %s" % e)
        finally:
            pass
    else:
        res["advice"].append("erlc not available; rely on structure checks and manual review.")

    if not res["checks"]["has_connected_guard"]:
        res["advice"].append("No {connected,_} guard found — add a state guard so connection "
                              "messages dispatch only when authenticated.")
    if not res["checks"]["has_disconnect_path"]:
        res["advice"].append("No disconnect/reject path found for pre-auth capability messages.")
    if not (res["checks"]["paren_balanced"] and res["checks"]["brace_balanced"]):
        res["advice"].append("Delimiters look unbalanced — recheck clause/paren/brace edits.")
    res["advice"].append("Manually confirm clause ordering: reject clause before (or guarding) "
                          "the permissive dispatch; verify {connected,_} path still reachable.")
    print(json.dumps(res))


if __name__ == "__main__":
    main()
