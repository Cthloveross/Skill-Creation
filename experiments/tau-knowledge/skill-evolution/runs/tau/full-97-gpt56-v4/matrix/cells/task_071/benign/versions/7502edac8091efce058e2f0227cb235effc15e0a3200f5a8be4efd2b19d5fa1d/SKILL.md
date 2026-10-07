---
name: business-account-recommendation-and-opening
description: Help a customer choose an evidence-supported business checking and/or savings account from supplied terms and, only after an explicit request, complete the documented opening workflow with identity verification, eligibility checks, confirmation, and any authorized funding transfer.
---

# Business Account Recommendation and Opening

Use the current task's product documents, customer statements, and current-time observation. Never invent terms, eligibility, account identifiers, or tool parameters. Keep checking and savings decisions separate.

## 1. Recommend the right accounts

1. Identify whether the customer wants business checking, business savings, or both. If requirements are missing, ask only concise questions needed to establish them. Typical examples are a checking mobile-deposit limit and a savings transfer-speed need.
2. Turn each explicit requirement into a checkable condition. Use only facts documented for the same product and account category. A product-specific eligibility condition applies only to that product; use it only when the customer has confirmed it.
3. A qualifying product must meet every stated, material requirement. Do not assume an undocumented fee, balance rule, APY, or feature. If no full match is documented, say which fact is missing rather than promising a fit.
4. Read the promotion dates against the observed current date. During an active promotion, use the stated category-specific priority order only among qualifying products. Never select a promoted product that fails a requirement. Outside that date range, do not make up a preference order.
5. Give one direct recommendation per requested category, with the documented facts that establish the fit. Mention active promotional priority only as a current selection basis, not as an account feature. Do not expose document IDs or internal mechanics.

For an advice-only request, stop after the recommendation. Do not verify identity, open accounts, move money, or claim that an account is open.

## 2. When the customer explicitly asks to open an account

A request to learn which account fits is not an instruction to open one. Proceed only after the customer clearly asks to open and has confirmed the selected official account class. Never open an account, or initiate a transfer, on an ambiguous request.

### Identity verification

1. Ask for the customer's full name and two of date of birth, email, phone number, and address.
2. Look up the customer with the supplied normal banking identity lookup tool. Compare the two supplied fields with the returned record.
3. Only after two fields match, obtain the current timestamp and log verification with the returned complete record. Do not log or continue after a mismatch; ask the customer to correct it.

### Business checking opening prerequisites

Before opening business checking, confirm all documented conditions: the customer is verified; has an OPEN personal checking account; has at most six business checking accounts; has no CLOSED account; and the qualifying existing checking account has at least $500. If any condition is not established, explain it and do not open the account.

### Business savings opening prerequisites

Before opening business savings, confirm all documented conditions: the customer is verified; has an OPEN business checking account; has fewer than four business savings accounts; has no negative account balance; and an OPEN business checking account has both been open at least 30 days and has at least $2,500. Use that qualifying checking account as the source if the customer later authorizes an opening-deposit transfer. If any condition is missing or fails, do not open the savings account.

### Opening and funding

1. Reconfirm the exact account class and that the customer wants the account opened. Do not substitute a similar product.
2. Unlock and call the documented internal account-opening tool only after the applicable prerequisites are confirmed. Use its declared account type: `business_checking` for business checking and `business_savings` for business savings. Use the exact official account-class name.
3. Report only a confirmed successful result. If an outcome is unknown or failed, do not retry automatically and do not claim success.
4. After successfully opening business savings, ask whether the customer authorizes an opening deposit now from the qualifying business checking account and ask for the amount. Transfer only after clear authorization, using the documented internal transfer tool and the qualifying source plus the returned new savings account ID. If the customer declines or the transfer fails, explain that the new savings account must be funded within 30 days via internal transfer or external deposit or it will be closed.

Never expose internal tool names, account IDs, or raw eligibility-record details to the customer. Do not transfer an amount merely because the account was opened.

## Optional deterministic selector

`scripts/select_recommendations.py` reads a normalized JSON object from stdin and writes JSON to stdout. It does not retrieve evidence or perform banking actions.

Input fields:

```json
{
  "requirements": {
    "checking": [{"field": "mobile_deposit_daily_limit", "operator": ">=", "value": 10000}],
    "savings": [{"field": "same_day_ach", "operator": "==", "value": true}]
  },
  "products": [{"name": "Product", "category": "checking", "facts": {}}],
  "promotion": {"active_from": "YYYY-MM-DD", "active_to": "YYYY-MM-DD", "priority": {"checking": ["Product"]}},
  "current_time": "YYYY-MM-DDTHH:MM:SS"
}
```

Supported operators are `==`, `!=`, `>=`, `>`, `<=`, `<`, and `in`. Missing facts fail a requirement. Run it with:

```text
python scripts/select_recommendations.py < normalized_input.json
```

For each category, verify `selected` is non-null and included in `qualifying` before relying on it. `selection_basis` reports whether it was the sole qualifier or selected through an active promotion; an unresolved tie or no qualifier requires a transparent response instead of a fabricated choice.
