"""Inspect the problem manifest and every referenced input file.

stdin:  {"problem": <path>, "root": <dir>}  (both optional)
stdout: JSON { "problem": <path>, "root": <dir>, "tasks": [ {id, description,
        input, output, input_resolved, output_resolved, input_kind, input_desc},
        ... ] }
where input_desc summarizes shape/dtype/preview per array (dict for .npz).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def main():
    problem, root = common.read_config()
    out = {"problem": problem, "root": root, "tasks": []}
    try:
        tasks = common.load_tasks(problem)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"failed to load manifest: {e}"
        print(json.dumps(out))
        return
    for t in tasks:
        rec = {
            "id": t.get("id"),
            "description": t.get("description"),
            "input": t.get("input"),
            "output": t.get("output"),
        }
        ip = t.get("input")
        if ip:
            ipr = common.resolve(root, ip)
            rec["input_resolved"] = ipr
            try:
                kind, data = common.load_input(ipr)
                rec["input_kind"] = kind
                if kind == "npz":
                    rec["input_desc"] = {k: common.describe_array(v) for k, v in data.items()}
                else:
                    rec["input_desc"] = common.describe_array(data)
            except Exception as e:  # noqa: BLE001
                rec["input_error"] = str(e)
        if t.get("output"):
            rec["output_resolved"] = common.resolve(root, t.get("output"))
        out["tasks"].append(rec)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
