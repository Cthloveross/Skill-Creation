#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bootstrap.sh [--python PATH]

Validate an existing Python 3.10+ environment for the AppWorld preliminary
experiment. This command does not create an environment, install packages, or
modify experiment data.

Options:
  --python PATH  Interpreter to validate (default: <project>/.venv/bin/python)
  -h, --help     Show this help text
EOF
}

script_directory="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_root="$(CDPATH= cd -- "${script_directory}/../../../.." && pwd -P)"
python_binary="${project_root}/.venv/bin/python"

while (($#)); do
  case "$1" in
    --python)
      if (($# < 2)); then
        echo "error: --python requires a path" >&2
        exit 2
      fi
      python_binary="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -x "${python_binary}" ]]; then
  echo "error: Python interpreter is not executable: ${python_binary}" >&2
  exit 2
fi

"${python_binary}" - "${project_root}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

project_root = Path(sys.argv[1]).resolve()
if sys.version_info < (3, 10):
    raise SystemExit("error: AppWorld preliminary requires Python 3.10 or newer")

try:
    import r2sp
    import yaml
except ImportError as exc:
    raise SystemExit(f"error: required project environment is incomplete: {exc}") from exc

r2sp_path = Path(r2sp.__file__).resolve()
try:
    r2sp_path.relative_to(project_root)
except ValueError as exc:
    raise SystemExit(
        "error: interpreter does not import r2sp from this project checkout"
    ) from exc

print(
    json.dumps(
        {
            "appworld_preliminary_environment": "valid",
            "project_root": str(project_root),
            "python": str(Path(sys.executable).resolve()),
            "python_version": ".".join(str(value) for value in sys.version_info[:3]),
            "pyyaml_version": yaml.__version__,
            "r2sp_path": str(r2sp_path),
        },
        sort_keys=True,
    )
)
PY
