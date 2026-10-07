#!/usr/bin/env python3
"""Advisory source guard for a Next.js performance repair.

Input on stdin is JSON ``{"app_root": "/app"}``. Output is JSON with ``ok``,
``checks``, and ``warnings``. The guard reads only source files and does not
modify the application. It cannot establish runtime timing or UI behavior;
run the production build and end-to-end checks as documented in SKILL.md.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def check(items: list[dict[str, Any]], name: str, passed: bool, detail: str,
          *, essential: bool = False) -> None:
    items.append({
        "name": name,
        "status": "pass" if passed else ("fail" if essential else "warning"),
        "detail": detail,
    })


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
    if not root.is_dir():
        print(json.dumps({"ok": False, "error": f"app_root does not exist: {root}"}))
        return 2

    checks: list[dict[str, Any]] = []
    warnings = ["This is a structural reminder only; validate build, routes, and browser behavior separately."]
    card = read(root / "src/components/ProductCard.tsx")
    check(checks, "product_card_mark_retained", "performance.mark(" in card,
          "ProductCard contains performance instrumentation.", essential=True)
    check(checks, "product_card_memoized", bool(re.search(r"\b(?:React\.)?memo\s*\(", card)),
          "ProductCard has a memo wrapper.")

    product_list = read(root / "src/components/ProductList.tsx")
    check(checks, "stable_cart_callback", "useCallback" in product_list and "setCart(prev" in product_list,
          "The cart handler appears to use a stable callback and functional update.")
    check(checks, "memoized_list_derivations", "useMemo" in product_list,
          "Product list contains memoized derived work.")

    source_root = root / "src"
    all_tsx = "\n".join(read(path) for path in source_root.rglob("*.tsx")) if source_root.is_dir() else ""
    check(checks, "advanced_testid_retained", 'data-testid="advanced-content"' in all_tsx or
          "data-testid={'advanced-content'}" in all_tsx,
          "The required advanced-content test hook exists.", essential=True)
    compare = read(root / "src/app/compare/page.tsx")
    dynamic_import = bool(re.search(r"dynamic\s*\(\s*\(\s*\)\s*=>\s*import\(", compare, re.S))
    check(checks, "advanced_dynamic_module_boundary", dynamic_import,
          "Compare page has a next/dynamic module import.")
    check(checks, "heavy_math_not_in_compare_entry", "from 'mathjs'" not in compare and
          'from "mathjs"' not in compare,
          "Compare entry does not statically import mathjs.")

    home = read(root / "src/app/page.tsx")
    if home:
        uses_all = "Promise.all" in home
        check(checks, "homepage_parallel_reads", uses_all,
              "Homepage has a Promise.all for independent server reads.")

    products_route = read(root / "src/app/api/products/route.ts")
    if products_route:
        check(checks, "products_route_parallel_reads", "Promise.all" in products_route,
              "Products route has a concurrent read group.")
        analytics_awaited = bool(re.search(r"await\s+logAnalyticsToService", products_route))
        analytics_observed = "logAnalyticsToService" in products_route and ".catch(" in products_route
        check(checks, "analytics_not_on_response_path", not analytics_awaited and analytics_observed,
              "Noncritical analytics is unawaited and has rejection handling.")

    checkout = read(root / "src/app/api/checkout/route.ts")
    if checkout and "fetchProfileFromService" in checkout:
        # A Promise.all before a later direct `await fetchProfile...` serializes
        # the dependent request behind unrelated work. Require a promise chain
        # and an aggregate wait to flag this common dependency-graph mistake.
        chained = bool(re.search(r"\w+Promise\.then\s*\([^=]*=>\s*fetchProfileFromService", checkout, re.S))
        aggregate_wait = "Promise.all" in checkout
        serial_profile = bool(re.search(r"await\s+fetchProfileFromService", checkout))
        check(checks, "dependent_profile_starts_from_prerequisite", chained and aggregate_wait and not serial_profile,
              "Dependent profile request appears chained from its prerequisite while independent work remains in flight.")

    failed = any(item["status"] == "fail" for item in checks)
    print(json.dumps({"ok": not failed, "checks": checks, "warnings": warnings}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
