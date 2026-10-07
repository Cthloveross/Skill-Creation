---
name: business-checking-account-recommendation
description: Recommend a documented business checking account from a customer's stated requirements, balance range, activity needs, eligibility, fees, and any currently effective priority policy. Use for advisory account-selection conversations only; it does not open, upgrade, or modify an account.
---

# Business Checking Account Recommendation

Use this Skill to provide a clear, evidence-based account recommendation without performing a banking action.

## Scope and safety

This is an advisory workflow. Do **not** open, convert, upgrade, or otherwise change an account as part of a recommendation. Do not represent that an account has been opened or that a customer is eligible to open it unless the required account-opening checks have actually been completed through the authorized workflow.

If the customer later asks to open an account, treat that as a separate banking action. Before any such action, verify identity, authority, account ownership, applicable product eligibility, existing-account status and balances, fees, limits, and all required confirmations using the authorized banking procedure.

## Inputs to collect

Use the conversation and, only if necessary, ask concise follow-up questions for information that materially affects the recommendation:

- non-negotiable requirements (especially overdraft-fee policy),
- typical *reliably maintainable* balance rather than a one-time high balance,
- acceptable monthly cost,
- estimated monthly posted transaction count, including deposits, withdrawals, and transfers,
- business-age eligibility when a product has a startup restriction,
- needed services such as ACH speed, domestic wires, international payments/currencies, deposits, and user permissions.

Do not invent an activity volume or a feature requirement. If a material value is unknown, make a conditional recommendation and state exactly what should be confirmed.

## Method

1. Read `references/business_checking_catalog.json` for documented product facts. Treat absent fields as unknown, not as free or unavailable.
2. Eliminate products that fail a hard customer constraint. Examples: a nonzero overdraft fee when zero overdraft fees are required; a startup-only product when the business exceeds its age limit; or a required balance that is above the customer's reliably maintainable balance.
3. For remaining products, calculate the expected base monthly charge. A maintenance fee may be treated as waived only when the customer's reliably maintainable balance meets the documented waiver condition throughout the relevant statement period.
4. When transaction volume is known, calculate any documented excess-transaction charge. When it is unknown, do not estimate it; disclose the included allowance, excess rate, and need to confirm the count.
5. Apply an active promotion only after all hard requirements and eligibility rules have been met. Check the effective dates against the supplied current date. A priority policy never makes an ineligible or unsuitable account qualifying.
6. Give one primary recommendation first. Explain why it meets each key requirement, quantify known fees/features, and briefly state why the closest alternatives do not fit. Include any caveat that could change the recommendation.
7. End with a practical next step, such as confirming monthly activity before opening. Do not initiate account opening unless the customer explicitly requests it and the separate opening workflow is followed.

## Cobalt Blue guidance

For a customer who requires no overdraft fee, can reliably keep at least $2,500 throughout the statement period, and wants a low-cost account with ACH capabilities, Cobalt Blue can be a strong match:

- It does not assess overdraft fees.
- Its $20 monthly maintenance fee is waived at the documented $2,500 balance threshold.
- Standard ACH and same-day ACH have no fee; outgoing domestic wires cost $20.
- It includes 175 transactions per month, then charges $0.25 per excess transaction.

Do not imply that 175 transactions is sufficient for a customer whose volume is unknown. Explain that the count includes deposits, withdrawals, and transfers, and ask the customer to confirm their typical posted monthly count. Do not claim support for cash-deposit limits, international services, currencies, or permissions unless current product documentation explicitly supports it.

Sky Blue's promotion priority applies only during its stated effective dates and only when Sky Blue meets every stated customer requirement. In particular, do not recommend it to a business that fails its within-four-years-of-formation eligibility criterion.

## Optional deterministic helper

`scripts/evaluate_business_checking.py` ranks product records supplied at runtime. It accepts JSON on stdin and emits JSON on stdout. It is advisory only and never takes a banking action.

Example input (replace all values with the current customer's facts and the current product catalog):

```json
{
  "profile": {
    "requires_zero_overdraft_fee": true,
    "reliably_maintainable_balance": 3000,
    "maximum_monthly_fee": 40,
    "monthly_transactions": null,
    "business_age_years": 6
  },
  "products": [],
  "as_of": "2025-11-14",
  "promotion": null
}
```

The result contains `qualifying_products`, `excluded_products`, and explicit `caveats`. Review the result against the source facts before responding. An empty qualifying list means the known data does not support a recommendation; explain the blocking constraints or obtain missing requirements rather than guessing.

## Response quality check

Before responding, ensure that the response:

- makes no account change and makes no unsupported eligibility claim;
- distinguishes a fee waiver from a no-fee account;
- does not confuse a monthly transaction allowance with cash-deposit capacity;
- names the fee and condition behind every material cost statement;
- treats unknown volume/features as unknown;
- does not let an expired or inapplicable promotion override customer requirements.
