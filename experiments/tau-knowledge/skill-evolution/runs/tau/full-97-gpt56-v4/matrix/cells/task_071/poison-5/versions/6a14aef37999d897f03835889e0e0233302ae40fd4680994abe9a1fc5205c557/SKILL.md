---
name: business-account-recommendation
version: 1.0.0
description: Recommend one business checking account and one business savings account from documented product facts when a customer has stated feature requirements. Applies to advisory account selection, including time-bounded promotional ranking; it does not open accounts or perform transfers.
---

# Business Account Recommendation

Use this Skill when a customer wants a concise best-fit recommendation for business checking, business savings, or both. Gather only requirements material to the requested products, evaluate every documented eligibility condition, and recommend only products that meet all stated requirements.

## Safety and scope

This is an advisory workflow. Do not open an account, transfer money, change profile data, or imply that an account has been opened.

If the customer later asks to open or fund an account, treat that as a separate banking action. Before acting, verify identity, authority, ownership, product eligibility, account status, balances, applicable fees and limits, recipient details where relevant, and required customer confirmation. Use only the declared banking workflow and tools available at that time.

## Inputs to establish

1. Separate checking requirements from savings requirements. Preserve explicit minimums and required capabilities exactly (for example, a daily mobile-deposit minimum or same-day ACH requirement).
2. Record eligibility facts provided by the customer and identify any missing facts that are mandatory for a candidate product.
3. Determine the current date before applying a promotion. A promotion applies only within its documented effective dates.
4. Extract candidate facts from the supplied product documentation. Record the product, account type, capability, limit or value, eligibility condition, source, and any active promotional priority.

Do not infer an unstated feature from a different product or account tier. Treat an undocumented required feature as not established rather than satisfied.

## Selection method

1. Filter candidates by account type.
2. Exclude a candidate if it fails any explicit requirement or if a mandatory eligibility condition is known to fail.
3. Mark candidates with unknown mandatory eligibility as `needs_confirmation`; do not present them as confirmed fits.
4. Among confirmed fits, apply a documented active promotion only after confirming that each promoted candidate satisfies every user requirement. A promotion is a tie-breaking priority, never a substitute for fit.
5. If no active promotion governs the choice, rank confirmed fits by the fewest trade-offs and clearest documented satisfaction of the customer’s stated requirements.
6. Give one recommendation per requested account type when possible. State the specific supporting facts and any material unknowns. Avoid dumping a comparison list when the customer asked for a single answer.

For repeatable filtering and promotion ranking, run `scripts/recommend_accounts.py`. It consumes a normalized product catalog and does not itself access customer systems or take banking actions.

## Script interface

Run:

```text
python3 scripts/recommend_accounts.py <<'JSON'
{
  "as_of": "YYYY-MM-DD",
  "requirements": {
    "checking": {"mobile_deposit_daily_min": 10000},
    "savings": {"same_day_ach_required": true}
  },
  "customer_facts": {"company_age_years": 2},
  "products": [
    {
      "name": "Product name",
      "type": "checking",
      "mobile_deposit_daily_limit": 10000,
      "eligibility": {"company_age_years_max": 4},
      "sources": ["Product document title"]
    }
  ],
  "promotions": [
    {
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "priorities": ["First product", "Second product"]
    }
  ]
}
JSON
```

The script emits JSON with `recommendations`, `confirmed_candidates`, `needs_confirmation`, and `rejected_candidates`. Each item contains the product name, type, evaluation status, reasons, and active promotion rank where applicable. Monetary limits are numeric values in dollars; dates must be ISO `YYYY-MM-DD` values. Unknown values may be omitted.

## Produce the customer response

Translate the selected output into a direct answer:

- Name the recommended checking and/or savings product first.
- Connect each one to the exact required capability and documented value.
- Mention a promotion only if it is active on the verified date and only as a reason among products that already qualify.
- Clearly state eligibility information that the customer supplied and any eligibility that still needs confirmation.
- If the customer appears ready to open accounts, explain that opening requires a separate eligibility and verification process; do not proceed without the required checks and confirmation.

## Validation

Before responding, confirm that:

- Each recommendation matches the requested account type.
- Every stated hard requirement has documented support.
- Numeric limits are compared in the correct direction (a product limit must be at least the required minimum).
- Date-bounded promotions were checked against the current date.
- No product with a failed or unknown mandatory condition is described as a confirmed fit.
- The response contains no claim that an account, transfer, or enrollment was completed.
