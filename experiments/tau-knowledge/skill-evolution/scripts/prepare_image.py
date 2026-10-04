#!/usr/bin/env python3
"""Build the fixed-dependency image and record its actual local content digest."""

import hashlib
import json
import subprocess
from pathlib import Path

runtime = Path(__file__).resolve().parent.parent / "runtime"
lock = json.loads((runtime / "image-lock.json").read_text())
subprocess.run(["docker", "build", "--tag", lock["image"], str(runtime)], check=True)
result = subprocess.check_output(["docker", "image", "inspect", lock["image"]], text=True)
lock["digest"] = json.loads(result)[0]["Id"]
lock["digest_kind"] = "image_id"
lock["dependency_hash"] = hashlib.sha256((runtime / "requirements.lock").read_bytes()).hexdigest()
(runtime / "image-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
print(lock["digest"])
