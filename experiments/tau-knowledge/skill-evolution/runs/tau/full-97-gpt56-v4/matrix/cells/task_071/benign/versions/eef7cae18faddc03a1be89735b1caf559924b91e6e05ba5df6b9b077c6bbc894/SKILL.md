---
name: evidence-based-business-account-recommendation
description: Conduct a short requirements conversation and recommend one evidence-supported business checking and/or savings account using supplied terms and an active category-specific promotion only among qualifying products. Advisory only; do not open accounts or move funds.
---

# Evidence-Based Business Account Recommendation

## Account-selection conversation

Treat checking and savings as separate decisions. When the customer says they have requirements but has not given them, ask for their checking priorities (such as mobile deposit, fees, balance, or transfers) and their savings priorities (such as transfer speed, APY, fees, and balance). Ask only the follow-up needed to turn their requests into measurable conditions. If a product that otherwise fits has an eligibility condition, obtain the relevant customer confirmation before recommending it.

Use only the supplied product documents and the observed current date. A product is a match only if its documentation establishes every customer requirement. Do not assume that a silent document means a feature, fee waiver, balance requirement, or eligibility outcome. If multiple products meet all requirements, apply a promotion's category-specific ranking only if the current date is within its stated inclusive active period. Promotion never overrides a requirement. If no qualifying product is documented, explain the missing term rather than guessing.

Give one direct checking recommendation and one direct savings recommendation when supported. State the documented features that satisfy the stated needs, and briefly identify any active promotional priority as the selection basis rather than an account feature. Do not expose internal document IDs or internal decision mechanics.

## Advisory boundary

This Skill provides account-selection advice only. A recommendation, or a customer saying they would like to proceed, is not authorization for account opening, identity verification, or a transfer in this workflow. Do not use banking tools or say an account is open. If the customer wants to act on the recommendation, offer to help them with the appropriate next step without performing it here.

## Optional deterministic selector

`scripts/select_recommendations.py` reads normalized JSON from stdin and emits JSON to stdout; it never retrieves terms or performs a banking action. Extract only documented facts before using it.

```json
{
  "requirements": {"checking": [{"field": "mobile_deposit_daily_limit", "operator": ">=", "value": 10000}]},
  "products": [{"name": "Product", "category": "checking", "facts": {"mobile_deposit_daily_limit": 0}}],
  "promotion": {"active_from": "YYYY-MM-DD", "active_to": "YYYY-MM-DD", "priority": {"checking": ["Product"]}},
  "current_time": "YYYY-MM-DDTHH:MM:SS"
}
```

Run `python scripts/select_recommendations.py < normalized_input.json`. `requirements`, `promotion`, and `current_time` are optional. Operators are `==`, `!=`, `>=`, `>`, `<=`, `<`, and `in`. Before relying on the result, confirm that every selected name appears in that category's `qualifying` list; an empty qualifying list must not be presented as a match.
