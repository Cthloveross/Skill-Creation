#!/usr/bin/env python3
"""JSON stdin: {"destination": "/root"}; JSON stdout: {"written": [paths...]}.
Copies the ACC source templates packaged with this Skill into destination.
"""
import json
import shutil
import sys
from pathlib import Path


def main():
    try:
        request = json.load(sys.stdin)
        destination = Path(request["destination"]).expanduser().resolve()
        if not destination.is_dir():
            raise ValueError("destination must be an existing directory")
        refs = Path(__file__).resolve().parent.parent / "references"
        names = ("pid_controller.py", "acc_system.py", "simulation.py", "tune_acc.py")
        written = []
        for name in names:
            source = refs / name
            if not source.is_file():
                raise FileNotFoundError(str(source))
            target = destination / name
            shutil.copyfile(source, target)
            written.append(str(target))
        print(json.dumps({"written": written}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
