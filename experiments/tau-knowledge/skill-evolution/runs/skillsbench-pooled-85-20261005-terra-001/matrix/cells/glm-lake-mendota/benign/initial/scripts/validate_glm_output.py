#!/usr/bin/env python3
"""JSON stdin/stdout entrypoint for independent GLM NetCDF validation."""
import json
import sys
from glm_common import validate_output


def main() -> None:
    try:
        request = json.load(sys.stdin)
        required = ("observation_csv", "output_path", "start", "stop")
        missing = [key for key in required if not request.get(key)]
        if missing:
            result = {"ok": False, "error": "missing required keys", "missing": missing}
        else:
            result = validate_output(request["output_path"], request["observation_csv"], request["start"], request["stop"])
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
