#!/usr/bin/env python3
"""Copy ACC source references into an executor-selected directory.
stdin: {"output_dir": "/root"}; stdout: {"written": [absolute paths]}.
"""
import json
import shutil
import sys
from pathlib import Path

NAMES = ("pid_controller.py", "acc_system.py", "tune_pid.py", "simulation.py")

def main():
    request = json.load(sys.stdin)
    out = Path(request.get("output_dir", ".")).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1] / "references"
    written = []
    for name in NAMES:
        src = root / name
        if not src.is_file():
            raise FileNotFoundError("packaged reference missing: " + str(src))
        dst = out / name
        shutil.copyfile(src, dst)
        written.append(str(dst))
    print(json.dumps({"written": written}, sort_keys=True))

if __name__ == "__main__":
    main()
