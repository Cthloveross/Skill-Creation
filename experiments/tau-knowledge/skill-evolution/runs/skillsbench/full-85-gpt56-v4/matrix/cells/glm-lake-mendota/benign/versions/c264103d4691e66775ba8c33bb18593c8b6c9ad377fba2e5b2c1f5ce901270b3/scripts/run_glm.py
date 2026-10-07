#!/usr/bin/env python3
"""Run GLM after removing the declared output directory. JSON stdin -> JSON stdout."""
import json, shutil, subprocess, sys
from pathlib import Path


def main():
    try:
        spec = json.load(sys.stdin)
        config = Path(spec["config"]).resolve()
        output = Path(spec["output"]).resolve()
        binary = spec.get("glm_bin", "glm")
        timeout = float(spec.get("timeout_sec", 600))
        if not config.is_file():
            raise FileNotFoundError(f"configuration not found: {config}")
        # GLM resolves relative forcing and output paths from this directory.
        outdir = output.parent
        if outdir.exists():
            shutil.rmtree(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run([binary], cwd=str(config.parent), text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout, check=False)
        exists = output.is_file() and output.stat().st_size > 0
        print(json.dumps({"ok": proc.returncode == 0 and exists, "returncode": proc.returncode,
                          "output": str(output), "output_exists": exists,
                          "output_bytes": output.stat().st_size if exists else 0,
                          "log_tail": proc.stdout[-6000:]}))
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"ok": False, "error": "GLM timed out", "log_tail": (exc.stdout or "")[-6000:]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))

if __name__ == "__main__":
    main()
