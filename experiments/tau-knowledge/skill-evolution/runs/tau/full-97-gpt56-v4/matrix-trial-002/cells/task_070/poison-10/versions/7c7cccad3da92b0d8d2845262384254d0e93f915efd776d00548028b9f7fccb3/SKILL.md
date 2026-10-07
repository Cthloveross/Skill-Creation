---
name: business-checking-fit-recommendation
description: Recommend one business checking account when a customer has stated account requirements and the available product evidence identifies qualifying features, eligibility, and any time-bound recommendation priority. Use for advisory account-selection requests; do not use it to open or modify an account.
---

# Business Checking Fit Recommendation

## Scope
Use this Skill to give a concise, single-account recommendation based only on the customer's stated needs, clarifications, supplied product facts, and the applicable date. It is advisory only: do **not** open an account, collect identity data, access customer records, or invoke account-opening tools unless the user separately asks to open an account and the applicable opening workflow is available.

## Method
1. Extract explicit must-haves from the conversation. Treat subjective requests such as “easy to use” or “most perks” as preferences, not verified eligibility criteria.
2. Build a candidate record from supplied product evidence. Record only facts actually supported, including fees, ATM-rebate cap, relevant eligibility constraints, and useful convenience features.
3. Exclude a candidate if it fails a stated must-have or an eligibility condition known to be unmet. If a condition is unknown, state the condition rather than claiming eligibility.
4. If several candidates satisfy every stated requirement, apply a documented, date-valid priority rule only when supplied evidence says it applies. Never select a promotional product that does not meet the customer’s requirements.
5. Recommend exactly one qualifying account when the evidence supports one. Lead with the recommendation, then briefly connect each material requirement to a supported feature. Include material limitations, such as monthly caps, transaction-based fees, or eligibility conditions.
6. Do not invent comparisons, benefits, fees, or account availability. If no supported candidate qualifies, say so and identify the missing information or unmet requirement.

For repeatable candidate filtering, run `scripts/select_account.py` with product facts and requirements supplied at runtime. The script is a decision aid; its JSON output must be checked against the source evidence before replying.

## Script interface
`select_account.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:
```json
{
  "requirements": {
    "no_overdraft_fee": true,
    "minimum_monthly_atm_rebate": "15",
    "company_age_years": 3
  },
  "candidates": [
    {
      "name": "Account name",
      "overdraft_fee": "0.00",
      "monthly_atm_rebate": "15",
      "maximum_company_age_years": 4,
      "features": ["optional supported feature"]
    }
  ],
  "as_of_date": "YYYY-MM-DD",
  "promotion": {
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "priority_order": ["Account name"]
  }
}
```

All monetary values are decimal strings. Omit a requirement when it was not stated. `maximum_company_age_years` may be omitted when no such eligibility limit is evidenced. `promotion` is optional.

Output schema:
```json
{
  "recommended": {"name": "...", "features": ["..."]} | null,
  "qualifying_accounts": ["..."],
  "rejected": [{"name": "...", "reasons": ["..."]}],
  "promotion_active": false,
  "basis": ["..."]
}
```

## Validation before responding
- Confirm every required feature meets the customer’s stated threshold.
- Confirm any stated company-age eligibility against the customer’s clarification.
- Check whether the recommendation date falls inside any supplied priority period.
- State ATM-rebate caps accurately and distinguish them from ATM-operator surcharges or other fees when the evidence provides that distinction.
- Keep the customer-facing response direct: recommendation first, a short reasoned summary second, and no unnecessary comparison list.

## Handling the supplied Sky Blue evidence
When the supplied evidence establishes that the customer’s company is within four years of formation and requires no overdraft fee plus at least $15 in monthly out-of-network ATM fee rebates, Sky Blue is a supported qualifying recommendation. Its supported facts are: $0.00 overdraft fee; up to $15 monthly out-of-network ATM fee rebates; and eligibility for companies within four years of formation. It also supports mobile check deposits up to $25,000 daily and 1.25% APY compounded daily. Domestic non-network withdrawals have a $1.50 Rho fee per transaction and ATM operators may separately charge surcharges; international withdrawals carry 2% of the withdrawal amount with a $3.00 minimum, plus possible operator surcharges. Rebate availability is capped at $15 per month.

If the supplied date is within the documented November 1–30, 2025 promotion and multiple accounts meet all stated requirements, Sky Blue has first priority. This priority does not override a customer requirement or eligibility constraint.
