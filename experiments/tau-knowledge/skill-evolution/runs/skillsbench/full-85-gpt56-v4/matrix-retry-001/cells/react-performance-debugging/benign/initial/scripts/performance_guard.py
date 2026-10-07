#!/usr/bin/env python3
"""Advisory structural guard for a Next.js performance repair.

Input (stdin JSON): {"app_root": "/app"}.
Output (stdout JSON): {"ok": bool, "checks": [...], "warnings": [...]}.
This script does not modify project files and does not claim runtime performance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def add_check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid JSON input: {exc}"}))
        return 2
    root_value = payload.get("app_root")
    if not isinstance(root_value, str) or not root_value:
        print(json.dumps({"ok": False, "error": "app_root must be a nonempty string"}))
        return 2

    root = Path(root_value)
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not root.is_dir():
        print(json.dumps({"ok": False, "error": f"app_root does not exist: {root}"}))
        return 2

    card = root / "src/components/ProductCard.tsx"
    card_text = read(card)
    if not card_text:
        add_check(checks, "product_card_present", "warning", f"could not read {card}")
        warnings.append("ProductCard could not be inspected; manually verify marks and memoization.")
    else:
        marks = card_text.count("performance.mark(")
        add_check(checks, "product_card_marks", "pass" if marks else "fail",
                  f"found {marks} performance.mark() call(s)")
        memoed = "React.memo" in card_text or "memo(" in card_text
        add_check(checks, "product_card_memoization", "pass" if memoed else "warning",
                  "memoization token found" if memoed else "manually verify ProductCard is React.memo-wrapped")

    product_list = root / "src/components/ProductList.tsx"
    list_text = read(product_list)
    if list_text:
        callback = "useCallback" in list_text
        memo_value = "useMemo" in list_text
        add_check(checks, "list_stable_callback", "pass" if callback else "warning",
                  "useCallback found" if callback else "verify callback props to memoized cards are stable")
        add_check(checks, "list_memoized_derived_data", "pass" if memo_value else "warning",
                  "useMemo found" if memo_value else "verify costly derived list data is memoized where applicable")
    else:
        add_check(checks, "product_list_present", "warning", f"could not read {product_list}")

    compare = root / "src/app/compare/page.tsx"
    compare_text = read(compare)
    all_tsx = "\n".join(read(p) for p in (root / "src").rglob("*.tsx")) if (root / "src").exists() else ""
    advanced_marker = 'data-testid="advanced-content"' in all_tsx or "data-testid={'advanced-content'}" in all_tsx
    add_check(checks, "advanced_testid_retained", "pass" if advanced_marker else "fail",
              "advanced-content test ID found in source" if advanced_marker else "advanced-content test ID not found")
    if compare_text:
        dynamic = "next/dynamic" in compare_text or "dynamic(" in compare_text
        add_check(checks, "compare_dynamic_boundary", "pass" if dynamic else "warning",
                  "dynamic import token found" if dynamic else "verify optional advanced view is separately dynamically imported")
    else:
        add_check(checks, "compare_page_present", "warning", f"could not read {compare}")

    routes = list((root / "src/app/api").rglob("route.ts")) if (root / "src/app/api").exists() else []
    if routes:
        for route in routes:
            text = read(route)
            name = f"route_review_{route.relative_to(root)}"
            if "await " in text and "Promise.all" not in text:
                add_check(checks, name, "warning", "contains await but no Promise.all; inspect dependencies before accepting a waterfall")
            else:
                add_check(checks, name, "pass", "no obvious unreviewed sequential-await pattern")
    else:
        add_check(checks, "api_routes_present", "warning", "no route.ts files found under src/app/api")

    failed = any(item["status"] == "fail" for item in checks)
    print(json.dumps({"ok": not failed, "checks": checks, "warnings": warnings}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
