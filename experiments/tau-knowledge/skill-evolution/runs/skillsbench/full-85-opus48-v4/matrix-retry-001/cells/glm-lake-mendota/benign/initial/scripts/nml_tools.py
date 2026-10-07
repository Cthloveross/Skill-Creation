#!/usr/bin/env python3
"""Get or set namelist parameters.

stdin JSON: {"nml":..,"action":"get"|"set","params":{k:v,..},"block":optional}
- get: params may be a list of keys OR dict; returns current values.
- set: params is a dict; edits the file in place.
stdout JSON: {"values":{..}} for get, {"changed":[..]} for set.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glm_lib


def main():
    req = json.load(sys.stdin)
    text = glm_lib.read_text(req["nml"])
    action = req.get("action", "get")
    if action == "get":
        params = req.get("params", {})
        keys = params if isinstance(params, list) else list(params.keys())
        vals = {k: glm_lib.get_param(text, k) for k in keys}
        json.dump({"values": vals}, sys.stdout)
    else:
        params = req["params"]
        for k, v in params.items():
            text = glm_lib.set_param(text, k, v,
                                     block=req.get("block") or glm_lib.KEY_BLOCK.get(k))
        glm_lib.write_text(req["nml"], text)
        json.dump({"changed": list(params.keys())}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
