"""Re-load produced outputs and report their structure for manual cross-check.

stdin:  {"problem": <path>, "root": <dir>}  (both optional)
stdout: JSON listing each output path, whether it loads, and shape/dtype/preview.
This does not know the ground truth; use it to confirm outputs exist and look
consistent with each description (and compare small cases to a NumPy formula).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import common  # noqa: E402


def main():
    problem, root = common.read_config()
    out = {"root": root, "outputs": []}
    tasks = common.load_tasks(problem)
    for t in tasks:
        rec = {"id": t.get("id"), "output": t.get("output")}
        p = common.resolve(root, t.get("output", ""))
        cand = p if os.path.exists(p) else (p + ".npy" if os.path.exists(p + ".npy") else None)
        if cand is None:
            rec["exists"] = False
            out["outputs"].append(rec)
            continue
        rec["exists"] = True
        rec["path"] = cand
        try:
            obj = np.load(cand, allow_pickle=False)
            if isinstance(obj, np.lib.npyio.NpzFile):
                rec["arrays"] = {k: common.describe_array(obj[k]) for k in obj.files}
            else:
                rec["array"] = common.describe_array(obj)
        except Exception as e:  # noqa: BLE001
            rec["load_error"] = str(e)
        out["outputs"].append(rec)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
