---
name: business-account-selection-and-opening
description: Help a customer identify one documented business checking and one documented business savings account that meet their requirements, then open the selected accounts only after explicit authorization, successful identity verification, and all documented eligibility checks.
---

# Business Account Selection and Opening

## Account-selection conversation

Treat checking and savings as separate decisions. When the customer says they have requirements but has not given them, ask for their checking priorities (such as mobile deposit, fees, balance, or transfers) and their savings priorities (such as transfer speed, APY, fees, and balance). Ask only the follow-up needed to turn their requests into measurable conditions. If a product that otherwise fits has an eligibility condition, obtain the relevant customer confirmation before recommending it.

Use only the supplied product documents and the observed current date. A product is a match only if its documentation establishes every customer requirement. Do not assume that a silent document means a feature, fee waiver, balance requirement, or eligibility outcome. If multiple products meet all requirements, apply a promotion's category-specific ranking only if the current date is within its stated inclusive active period. Promotion never overrides a requirement. If no qualifying product is documented, explain the missing term rather than guessing.

Give one direct checking recommendation and one direct savings recommendation when supported. State the documented features that satisfy the stated needs, and briefly identify any active promotional priority as the selection basis rather than an account feature. Do not expose internal document IDs or internal decision mechanics.

## Opening workflow after an explicit request

Do not open an account merely because the customer asks for a recommendation. When the customer clearly asks to open the selected account(s), complete this sequence before any opening action:

1. **Confirm selection and authorization.** Confirm the exact official account class for every requested account. A recommendation plus a clear request to set it up can be confirmation; do not open additional accounts.
2. **Verify identity.** Ask for full name and two of date of birth, email, phone number, or address. Use the normal identity lookup with the provided identifier, compare two fields, then obtain the current timestamp and log verification with the full returned customer record. Do not proceed after a mismatch.
3. **Check business-checking eligibility.** Confirm: verified identity; at least one OPEN personal checking account; no more than six business checking accounts; no CLOSED accounts; and the qualifying existing checking account has at least $500.
4. **Check business-savings eligibility.** Confirm: verified identity; at least one OPEN business checking account; fewer than four business savings accounts; no negative balances; and an OPEN business checking account that has been open at least 30 days and has at least $2,500. Keep the ID of this qualifying checking account as the possible funding source.
5. If a required condition is absent or fails, explain the unmet condition and do not attempt the opening. Customer assertions may be used only when no supplied account lookup is available; do not claim an unverified condition was system-confirmed.
6. Unlock the documented account-opening agent tool and follow the signature it returns. Use the exact official account class and the appropriate business account type returned by the tool. Record success only from a successful tool result. Never retry an unknown result.

For business savings, after a successful opening, ask whether the customer authorizes an opening deposit from the identified qualifying business checking account and ask for the amount. Only after clear authorization, unlock and call the documented internal-transfer tool using that qualifying source, the new savings ID, and the authorized amount. If the customer declines or the transfer fails, tell them they have 30 days to fund the savings account by internal transfer or external deposit or it will close. Never expose internal tool names or account IDs to the customer.

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
