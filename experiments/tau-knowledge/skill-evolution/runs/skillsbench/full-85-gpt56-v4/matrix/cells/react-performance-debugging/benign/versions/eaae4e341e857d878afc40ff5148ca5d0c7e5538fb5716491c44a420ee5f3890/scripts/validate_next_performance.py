#!/usr/bin/env python3
"""Conservative source-contract checks for this Next.js performance task.
Input: {"root": "/path/to/app"}; Output: {"ok": bool, "errors": [...], "checks": {...}}.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        root = Path(payload["root"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid input: {exc}"], "checks": {}}))
        return 2

    errors: list[str] = []
    checks: dict[str, object] = {}
    card = read(root / "src/components/ProductCard.tsx")
    listing = read(root / "src/components/ProductList.tsx")
    compare = read(root / "src/app/compare/page.tsx")
    api_dir = root / "src/app/api"
    route_texts = [read(p) for p in api_dir.glob("**/route.ts")] if api_dir.exists() else []

    checks["product_card_exists"] = bool(card)
    checks["performance_marks_retained"] = "performance.mark(" in card
    if card and not checks["performance_marks_retained"]:
        errors.append("ProductCard has no performance.mark() call; preserve instrumentation.")

    checks["product_list_memoization"] = bool(re.search(r"\b(?:React\.)?memo\s*\(", listing))
    checks["product_list_stable_callback"] = "useCallback" in listing
    if listing and not checks["product_list_memoization"]:
        errors.append("ProductList does not visibly memoize a child component.")
    if listing and not checks["product_list_stable_callback"]:
        errors.append("ProductList does not visibly use useCallback for stable handler props.")

    checks["advanced_testid_present"] = 'data-testid="advanced-content"' in compare or any(
        'data-testid="advanced-content"' in read(p)
        for p in (root / "src").glob("**/*.tsx")
    )
    if not checks["advanced_testid_present"]:
        errors.append("advanced-content test id is missing from source.")

    dynamic_present = bool(re.search(r"\bdynamic\s*\(\s*\(\s*\)\s*=>\s*import\s*\(", compare, re.S))
    checks["compare_dynamic_import"] = dynamic_present
    if compare and not dynamic_present:
        errors.append("Compare page has no visible Next dynamic import boundary.")

    promise_routes = sum("Promise.all" in text for text in route_texts)
    checks["api_routes_with_promise_all"] = promise_routes
    checks["api_route_count"] = len(route_texts)
    if route_texts and promise_routes == 0:
        errors.append("No API route visibly uses Promise.all; inspect independent upstream calls.")

    print(json.dumps({"ok": not errors, "errors": errors, "checks": checks}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
