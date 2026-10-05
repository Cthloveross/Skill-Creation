#!/usr/bin/env python3
"""Evaluate documented business-checking candidates against hard requirements.

Reads one JSON object from stdin and writes one JSON object to stdout. It uses only
packaged product facts and does not call banking systems or open an account.
"""

import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "product_catalog.json"


def decimal_value(value, field):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a number")
    if parsed < 0:
        raise ValueError(f"{field} must not be negative")
    return parsed


def parse_date(value):
    if value is None:
        return None
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", str(value))
    if not match:
        raise ValueError("as_of must contain an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(match.group(1))
    except ValueError as exc:
        raise ValueError("as_of must contain a valid ISO date") from exc


def normalize_requirements(raw):
    if not isinstance(raw, dict):
        raise ValueError("requirements must be an object")
    normalized = {}

    if "company_age_years" in raw:
        normalized["company_age_years"] = decimal_value(raw["company_age_years"], "company_age_years")
    elif "company_within_four_years" in raw:
        if not isinstance(raw["company_within_four_years"], bool):
            raise ValueError("company_within_four_years must be a boolean")
        normalized["company_within_four_years"] = raw["company_within_four_years"]

    if "max_overdraft_fee" in raw:
        normalized["max_overdraft_fee"] = decimal_value(raw["max_overdraft_fee"], "max_overdraft_fee")
    elif raw.get("requires_zero_overdraft_fee") is True:
        normalized["max_overdraft_fee"] = Decimal("0")
    elif "requires_zero_overdraft_fee" in raw and not isinstance(raw["requires_zero_overdraft_fee"], bool):
        raise ValueError("requires_zero_overdraft_fee must be a boolean")

    if "minimum_atm_rebate_per_month" in raw:
        normalized["minimum_atm_rebate_per_month"] = decimal_value(
            raw["minimum_atm_rebate_per_month"], "minimum_atm_rebate_per_month"
        )

    if "requires_dedicated_manager" in raw:
        if not isinstance(raw["requires_dedicated_manager"], bool):
            raise ValueError("requires_dedicated_manager must be a boolean")
        if raw["requires_dedicated_manager"]:
            normalized["requires_dedicated_manager"] = True

    return normalized


def evaluate_product(product, requirements):
    reasons = []

    if "company_age_years" in requirements:
        limit = product.get("company_age_max_years")
        if limit is not None and requirements["company_age_years"] > Decimal(str(limit)):
            reasons.append(f"company age exceeds the documented {limit}-year eligibility limit")
    elif requirements.get("company_within_four_years") is False:
        limit = product.get("company_age_max_years")
        if limit is not None and Decimal(str(limit)) <= Decimal("4"):
            reasons.append("customer reports the company is not within the documented four-year eligibility limit")

    if "max_overdraft_fee" in requirements:
        documented = product.get("overdraft_fee")
        if documented is None:
            reasons.append("overdraft-fee amount is not documented")
        elif Decimal(str(documented)) > requirements["max_overdraft_fee"]:
            reasons.append("documented overdraft fee exceeds the requested maximum")

    if "minimum_atm_rebate_per_month" in requirements:
        documented = product.get("atm_rebate_cap_per_month")
        if documented is None:
            reasons.append("monthly ATM-rebate cap is not documented")
        elif Decimal(str(documented)) < requirements["minimum_atm_rebate_per_month"]:
            reasons.append("documented monthly ATM-rebate cap is below the requested minimum")

    if requirements.get("requires_dedicated_manager") and product.get("dedicated_manager") is not True:
        reasons.append("dedicated-manager support is not documented")

    return reasons


def display_money(value):
    return f"${Decimal(str(value)):.2f}"


def product_output(product):
    result = {"name": product["name"], "facts": product["facts"]}
    for key in (
        "overdraft_fee",
        "atm_rebate_cap_per_month",
        "monthly_fee",
        "monthly_fee_waiver_balance",
        "minimum_balance_for_benefits",
        "free_period_months",
        "company_age_max_years",
        "dedicated_manager",
    ):
        if product.get(key) is not None:
            result[key] = product[key]
    return result


def make_customer_summary(product):
    pieces = []
    if product.get("overdraft_fee") is not None:
        pieces.append(f"Its documented overdraft fee is {display_money(product['overdraft_fee'])}.")
    if product.get("atm_rebate_cap_per_month") is not None:
        pieces.append(
            "Its documented cap for eligible out-of-network ATM-fee rebates is "
            f"{display_money(product['atm_rebate_cap_per_month'])} per month."
        )
    if product.get("dedicated_manager") is True:
        pieces.append("It includes documented dedicated-manager support.")
    return " ".join(pieces)


def make_caveats(product):
    caveats = []
    if product.get("monthly_fee") is not None:
        if product.get("free_period_months") is not None:
            caveats.append(
                f"After its {product['free_period_months']}-month free period, the documented monthly fee is "
                f"{display_money(product['monthly_fee'])}."
            )
        elif product.get("monthly_fee_waiver_balance") is not None:
            caveats.append(
                f"Its documented monthly fee is {display_money(product['monthly_fee'])}, waived at a "
                f"{display_money(product['monthly_fee_waiver_balance'])} balance."
            )
        else:
            caveats.append(f"Its documented monthly fee is {display_money(product['monthly_fee'])}.")
    if product.get("minimum_balance_for_benefits") is not None:
        caveats.append(
            f"The documented minimum end-of-day balance for account benefits is "
            f"{display_money(product['minimum_balance_for_benefits'])}."
        )
    caveats.append("ATM operator surcharges may be separate; only eligible documented fees count toward the monthly rebate cap.")
    return caveats


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        requirements = normalize_requirements(request.get("requirements"))
        if not requirements:
            raise ValueError("provide at least one supported hard requirement")
        as_of = parse_date(request.get("as_of"))
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

        qualifying = []
        disqualified = []
        for product in catalog["products"]:
            reasons = evaluate_product(product, requirements)
            if reasons:
                disqualified.append({"name": product["name"], "reasons": reasons})
            else:
                qualifying.append(product)

        promo = catalog["promotion"]
        active = bool(as_of and date.fromisoformat(promo["start"]) <= as_of <= date.fromisoformat(promo["end"]))
        promotion_result = {
            "applied": active,
            "rule": promo["rule"] if active else "No dated promotional ordering was applied.",
        }

        selected = None
        needed = []
        if len(qualifying) == 1:
            selected = qualifying[0]
        elif len(qualifying) > 1 and active:
            priority_index = {name: index for index, name in enumerate(promo["priority"])}
            qualifying.sort(key=lambda item: priority_index.get(item["name"], len(priority_index)))
            selected = qualifying[0]
        elif len(qualifying) > 1:
            needed.append(
                "More than one documented product meets the stated hard requirements. Ask which tie-breaker matters most, such as monthly-fee tolerance, balance requirement, dedicated support, or interest."
            )
        else:
            needed.append("No bundled candidate is documented to meet every stated hard requirement. Do not recommend a non-qualifying account.")

        output = {
            "selected": product_output(selected) if selected else None,
            "qualifying": [product_output(item) for item in qualifying],
            "disqualified": disqualified,
            "promotion": promotion_result,
            "needed_clarifications": needed,
            "customer_summary": make_customer_summary(selected) if selected else "",
            "caveats": make_caveats(selected) if selected else [],
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
