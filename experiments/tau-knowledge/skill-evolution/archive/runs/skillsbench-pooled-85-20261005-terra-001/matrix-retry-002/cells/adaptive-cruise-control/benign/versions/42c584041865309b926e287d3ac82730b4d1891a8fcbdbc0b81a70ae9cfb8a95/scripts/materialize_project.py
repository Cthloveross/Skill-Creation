#!/usr/bin/env python3
"""Copy packaged ACC sources into an executor-selected directory.
stdin: {"output_dir": "/root"}
stdout: {"written": [absolute_path, ...]}
"""
import json
import shutil
import sys
from pathlib import Path

NAMES = ("pid_controller.py", "acc_system.py", "tune_pid.py", "simulation.py")


def main():
    request = json.load(sys.stdin)
    output_dir = Path(request.get("output_dir", ".")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    references = Path(__file__).resolve().parents[1] / "references"
    written = []
    for name in NAMES:
        source = references / name
        if not source.is_file():
            raise FileNotFoundError("packaged reference missing: " + str(source))
        destination = output_dir / name
        shutil.copyfile(source, destination)
        written.append(str(destination))
    print(json.dumps({"written": written}, sort_keys=True))


if __name__ == "__main__":
    main()
