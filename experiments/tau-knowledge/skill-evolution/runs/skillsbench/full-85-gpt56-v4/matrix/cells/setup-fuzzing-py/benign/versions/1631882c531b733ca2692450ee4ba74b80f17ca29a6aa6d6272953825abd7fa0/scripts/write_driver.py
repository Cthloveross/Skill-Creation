#!/usr/bin/env python3
"""Write an Atheris driver for one explicitly selected public API.
Input JSON: library_dir, module, callable, input_kind (str, bytes, json_dict).
Output JSON: {ok, path, ...}. The target values are supplied at runtime.
"""
import json
import re
import sys
from pathlib import Path

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

TEMPLATE = '''#!/usr/bin/env python3
# Generated after library-specific API analysis.  See notes_for_testing.txt.
import sys
import atheris

with atheris.instrument_imports():
    import {module} as target_module


def _target_callable():
    value = target_module
    for name in {callable_parts!r}:
        value = getattr(value, name)
    return value


@atheris.instrument_func
def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
{input_build}
    try:
        _target_callable()(value)
    # Invalid fuzzed input is expected; do not hide BaseException or fuzzer failures.
    except Exception:
        pass


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
'''

BUILDS = {
    "str": "    value = fdp.ConsumeUnicodeNoSurrogates(4096)\n",
    "bytes": "    value = fdp.ConsumeBytes(4096)\n",
    # JSON serialization keeps a structured object while fuzzer controls keys and values.
    "json_dict": "    import json\n    pairs = fdp.ConsumeIntInRange(0, 16)\n    value = {fdp.ConsumeUnicodeNoSurrogates(64): fdp.ConsumeUnicodeNoSurrogates(256) for _ in range(pairs)}\n    value = json.loads(json.dumps(value))\n",
}


def main():
    try:
        req = json.load(sys.stdin)
        root = Path(req["library_dir"]).resolve()
        module, callable_name, kind = req["module"], req["callable"], req["input_kind"]
        if not root.is_dir():
            raise ValueError("library_dir is not a directory")
        if not IDENT.fullmatch(module) or not IDENT.fullmatch(callable_name):
            raise ValueError("module and callable must be dotted Python identifiers")
        if kind not in BUILDS:
            raise ValueError("input_kind must be str, bytes, or json_dict")
        text = TEMPLATE.format(module=module, callable_parts=callable_name.split("."), input_build=BUILDS[kind])
        destination = root / "fuzz.py"
        destination.write_text(text, encoding="utf-8")
        print(json.dumps({"ok": True, "path": str(destination), "module": module,
                          "callable": callable_name, "input_kind": kind}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)

if __name__ == "__main__":
    main()
