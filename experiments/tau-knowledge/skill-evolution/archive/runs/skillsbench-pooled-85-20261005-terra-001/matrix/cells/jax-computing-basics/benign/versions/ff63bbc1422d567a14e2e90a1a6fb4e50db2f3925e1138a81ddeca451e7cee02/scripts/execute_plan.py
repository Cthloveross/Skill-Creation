#!/usr/bin/env python3
"""Execute a complete declarative JAX plan for a problem manifest.

stdin schema:
{
  "manifest_path": "/app/problem.json",
  "plan": [{"id": <manifest task id>, "expr": <jax_task_helpers expression>,
            "expected_shape": [..], "expected_dtype": "float64", "archive_key": "result"}]
}

The plan must contain exactly one entry for every manifest item. .npy outputs contain the
computed array. .npz outputs contain it under archive_key, defaulting to "result".
"""
import json
import sys
from pathlib import Path
import numpy as np
from jax import config
config.update("jax_enable_x64", True)
import jax.numpy as jnp
from jax_task_helpers import evaluate


def resolve(base, value):
    p = Path(value)
    return p if p.is_absolute() else base / p


def load_environment(path: Path):
    raw = np.load(path, allow_pickle=False)
    env = {}
    if isinstance(raw, np.lib.npyio.NpzFile):
        try:
            for key in raw.files:
                env[key] = jnp.asarray(raw[key])
        finally:
            raw.close()
    else:
        env["input"] = jnp.asarray(raw)
        env[path.stem] = env["input"]
    return env


def validate(value, item):
    result = np.asarray(value)
    if item.get("expected_shape") is not None and tuple(result.shape) != tuple(item["expected_shape"]):
        raise ValueError(f"task {item['id']!r}: shape {result.shape}, expected {tuple(item['expected_shape'])}")
    if item.get("expected_dtype") is not None and result.dtype != np.dtype(item["expected_dtype"]):
        raise ValueError(f"task {item['id']!r}: dtype {result.dtype}, expected {item['expected_dtype']}")
    return result


def main():
    request = json.load(sys.stdin)
    manifest_path = Path(request.get("manifest_path", "/app/problem.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise ValueError("manifest must be a JSON list")
    task_by_id = {task["id"]: task for task in manifest}
    if len(task_by_id) != len(manifest):
        raise ValueError("manifest task ids must be unique")
    plan = request.get("plan")
    if not isinstance(plan, list):
        raise ValueError("request.plan must be a list")
    plan_by_id = {}
    for item in plan:
        if not isinstance(item, dict) or "id" not in item or "expr" not in item:
            raise ValueError("every plan entry requires id and expr")
        if item["id"] in plan_by_id:
            raise ValueError(f"duplicate plan entry for {item['id']!r}")
        plan_by_id[item["id"]] = item
    if set(plan_by_id) != set(task_by_id):
        missing, extra = set(task_by_id) - set(plan_by_id), set(plan_by_id) - set(task_by_id)
        raise ValueError(f"plan must cover manifest exactly; missing={list(missing)}, extra={list(extra)}")
    report = []
    for task in manifest:
        item = plan_by_id[task["id"]]
        env = load_environment(resolve(manifest_path.parent, task["input"]))
        result = validate(evaluate(item["expr"], env), item)
        output_path = resolve(manifest_path.parent, task["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix == ".npy":
            np.save(output_path, result)
        elif output_path.suffix == ".npz":
            np.savez(output_path, **{item.get("archive_key", "result"): result})
        else:
            raise ValueError(f"unsupported output extension {output_path.suffix!r}; use .npy or .npz")
        report.append({"id": task["id"], "path": str(output_path), "shape": list(result.shape), "dtype": str(result.dtype)})
    print(json.dumps({"written": report}, indent=2))


if __name__ == "__main__":
    main()
