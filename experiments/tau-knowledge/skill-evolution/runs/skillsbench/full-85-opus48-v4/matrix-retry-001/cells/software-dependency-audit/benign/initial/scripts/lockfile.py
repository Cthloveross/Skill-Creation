"""Parse an npm package-lock.json into resolved (name, version) pairs.

Supports lockfile v1 (recursive ``dependencies``) and v2/v3 (``packages`` map).
Returns a de-duplicated, sorted list of (name, version) tuples including
transitive dependencies. Entries without a concrete version (e.g. local linked
workspace packages) are skipped.
"""
import json


def _name_from_path(path):
    if "node_modules/" in path:
        return path.split("node_modules/")[-1]
    return path


def load_packages(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    found = {}

    packages = data.get("packages")
    if isinstance(packages, dict):
        for key, meta in packages.items():
            if key == "" or not isinstance(meta, dict):
                continue
            if meta.get("link") is True:
                continue
            name = _name_from_path(key)
            version = meta.get("version")
            if name and version:
                found[(name, version)] = True

    deps = data.get("dependencies")
    if isinstance(deps, dict):
        def walk(node):
            for name, meta in node.items():
                if not isinstance(meta, dict):
                    continue
                version = meta.get("version")
                if name and version:
                    found[(name, version)] = True
                child = meta.get("dependencies")
                if isinstance(child, dict):
                    walk(child)
        walk(deps)

    return sorted(found.keys())


if __name__ == "__main__":
    import sys
    pkgs = load_packages(sys.argv[1])
    for n, v in pkgs:
        print(f"{n}\t{v}")
