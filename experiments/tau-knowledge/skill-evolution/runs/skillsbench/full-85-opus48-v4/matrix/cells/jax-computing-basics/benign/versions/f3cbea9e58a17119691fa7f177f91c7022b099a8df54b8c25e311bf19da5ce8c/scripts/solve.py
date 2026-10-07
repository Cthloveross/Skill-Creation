"""End-to-end solver: read manifest, compute each task with JAX, save outputs.

stdin:  {"problem": <path>, "root": <dir>}  (both optional)
stdout: JSON { "root":..., "results": [ {id, input, output, status, handler?,
        output_shape?, output_dtype?, saved?, error?} ] }

Status is one of: ok | unhandled | error. 'ok' means a file was written; it does
NOT by itself prove the computation matches the description -- verify separately.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import common  # noqa: E402
import handlers  # noqa: E402


def main():
    problem, root = common.read_config()
    report = {"problem": problem, "root": root, "results": []}
    try:
        tasks = common.load_tasks(problem)
    except Exception as e:  # noqa: BLE001
        report["error"] = f"failed to load manifest: {e}"
        print(json.dumps(report))
        sys.exit(1)

    for t in tasks:
        res = {"id": t.get("id"), "input": t.get("input"), "output": t.get("output")}
        try:
            ipr = common.resolve(root, t["input"])
            kind, data = common.load_input(ipr)
            result = handlers.dispatch(t, kind, data)
            # materialize device arrays
            if isinstance(result, dict):
                mat = {k: np.asarray(v) for k, v in result.items()}
                res["output_shape"] = {k: list(v.shape) for k, v in mat.items()}
                res["output_dtype"] = {k: str(v.dtype) for k, v in mat.items()}
            else:
                mat = np.asarray(result)
                res["output_shape"] = list(mat.shape)
                res["output_dtype"] = str(mat.dtype)
            outp = common.resolve(root, t["output"])
            saved = common.save_output(outp, mat)
            res["saved"] = saved
            res["status"] = "ok"
        except handlers.Unhandled as u:
            res["status"] = "unhandled"
            res["error"] = str(u)
        except Exception as e:  # noqa: BLE001
            res["status"] = "error"
            res["error"] = f"{type(e).__name__}: {e}"
        report["results"].append(res)

    print(json.dumps(report, indent=2))
    # Non-zero exit if any task failed to produce a file.
    if any(r.get("status") != "ok" for r in report["results"]):
        sys.exit(2)


if __name__ == "__main__":
    main()
