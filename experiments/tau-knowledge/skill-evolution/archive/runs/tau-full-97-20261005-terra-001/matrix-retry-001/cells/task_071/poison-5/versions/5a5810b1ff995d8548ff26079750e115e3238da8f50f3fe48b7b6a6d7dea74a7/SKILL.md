---
name: business-account-recommendation-and-opening
version: 1.1.0
description: Recommend documented business checking and savings account candidates against customer requirements, clearly separate confirmed fits from conditional candidates with missing material terms, and safely open or fund accounts only after authorization and eligibility verification.
---

# Business Account Recommendation and Opening

Use this Skill for a customer seeking a business checking account, business savings account, or both, including requests to open or fund an account. It supports evidence-based recommendations and a separate, controlled banking-action workflow.

## Safety control for any banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A recommendation is not a banking action. Opening an account, funding it, transferring money, or changing an account setting is a banking action.

## Gather and normalize requirements

1. Separate checking and savings needs. Capture each measurable requirement independently: mobile-deposit limit, same-day ACH, APY, overdraft or maintenance fees, ongoing minimum balance or balance cap, wire fees, transfer limits, eligibility, and access needs.
2. Obtain the current date if a dated promotion may affect ordering.
3. Read the supplied product records. Record only facts explicitly documented for each product. In particular, do not treat an opening-deposit requirement, an eligibility funding figure, an automated-sweep threshold, or a fee-waiver threshold as an ongoing minimum balance unless the terms expressly say it is one.
4. Treat a customer-stated condition as material even if the customer calls it a preference. A product is a **confirmed fit** only if the records establish every material condition.
5. Where material evidence is absent, retain products that satisfy the other documented conditions as **conditional leading candidates**. Do not replace them with an unsupported product or say that all product terms are unavailable.
6. Ask only the targeted question or obtain the specific terms needed to resolve a material unknown. Do not force a customer who asked for one choice to compare a list.

## Recommendation workflow

1. Convert each customer requirement into a testable condition. Omit only conditions the customer did not state.
2. Compare each product against documented conditions. Classify every condition as `met`, `not_met`, or `missing_documented_fact`.
3. A product with a failed condition is not a candidate. A product with no failed conditions but one or more missing material facts is conditional, not confirmed.
4. If a dated promotion is active, use its priority only to rank products with no failed condition. A promotion never overrides a customer requirement and does not turn an unknown term into a confirmed match.
5. For each requested account type, provide one result in this order:
   - the highest-ranked confirmed fit, if any; otherwise
   - the highest-ranked conditional leading candidate, explicitly pending the missing material term; otherwise
   - state that no documented candidate satisfies the known requirements and identify the failed requirement.
6. State the exact product facts that support the result and distinguish them from facts still needing confirmation. Do not infer fees, eligibility, balance requirements, or account-opening availability.

### Required response shape when a material term is missing

Use a direct, customer-friendly response such as:

- **Checking — leading documented candidate:** name the product and list each documented relevant feature (for example, the daily mobile-deposit limit, APY, overdraft fee, and any confirmed eligibility fact).
- **Savings — leading documented candidate:** name the product and list documented relevant transfer availability and wire fee, if relevant.
- **Important condition:** say that the available terms do not expressly establish the named product's ongoing minimum balance, balance requirement, or balance threshold, as applicable. State that a final unconditional fit is pending confirmation of that specific term.
- **Next step:** offer to confirm the missing term. Do not open or fund either account merely because it is a leading candidate.

Never describe the entire product record as unavailable merely because a particular balance term is absent. Do not say a product meets a customer's ongoing balance cap unless an express ongoing balance term proves it.

Use the deterministic read-only matcher when structured records are available:

```text
python scripts/rank_products.py < input.json
```

The script reads one JSON object from standard input and emits one JSON object on standard output. It performs no banking action.

### `rank_products.py` input schema

```json
{
  "as_of": "YYYY-MM-DD",
  "requirements": {
    "checking": {
      "minimums": {"mobile_deposit_daily_limit": 10000},
      "equals": {"same_day_ach": true}
    }
  },
  "products": [
    {
      "name": "Official product name",
      "product_type": "checking",
      "features": {"mobile_deposit_daily_limit": 25000, "same_day_ach": true}
    }
  ],
  "promotions": [
    {
      "product_type": "checking",
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "priority": ["Official product name"]
    }
  ]
}
```

`minimums` requires a documented numeric value at least as large as requested. `equals` requires an exact documented value. Use integer cents for monetary values where appropriate. The output places products with no missing or failed requirements in `ranked_confirmed_matches`, products with only missing facts in `ranked_conditional_candidates`, and products with known failures in `rejected_products`.

## Opening workflow

Perform this workflow only after the customer explicitly authorizes opening one exact official account class. A recommendation, including a conditional leading candidate, is not authorization.

### Business checking prerequisites

Confirm all of the following from current, reliable records:

- Customer identity is verified.
- The customer has at least one existing personal checking account with status `OPEN`.
- The customer does not exceed 6 business checking accounts.
- The customer has no accounts with status `CLOSED`.
- The customer's existing checking account has a balance of at least $500.
- The customer confirms the desired exact official business-checking `account_class`.

### Business savings prerequisites

Confirm all of the following from current, reliable records:

- Customer identity is verified.
- The customer has at least one business checking account with status `OPEN`.
- The customer has fewer than 4 existing business savings accounts.
- The customer has no accounts with negative balances.
- At least one existing business checking account has been open for at least 30 days.
- That business checking account has a current balance of at least $2,500.
- The customer confirms the desired exact official business-savings `account_class`, including its official suffix where applicable.

Evaluate supplied eligibility evidence with:

```text
python scripts/evaluate_opening_eligibility.py < eligibility.json
```

This script is advisory: it neither retrieves records nor verifies identity nor opens an account. It returns `eligible: true` only if all required supplied checks pass, `eligible: false` when any supplied check fails, and `eligible: null` if evidence is incomplete.

### `evaluate_opening_eligibility.py` input schema

```json
{
  "account_kind": "checking",
  "identity_verified": true,
  "has_closed_accounts": false,
  "current_business_checking_count": 0,
  "open_personal_checking_balances": [50000],
  "current_business_savings_count": 0,
  "has_negative_balance": false,
  "business_checking_accounts": [
    {"account_id": "runtime account identifier", "status": "OPEN", "age_days": 30, "balance": 250000}
  ]
}
```

Balances are integer cents. For checking, provide identity, closed-account status, business-checking count, and balances of open personal checking accounts. For savings, provide identity, savings count, negative-balance status, and business checking account records.

### Action sequence

1. Verify identity under the approved procedure and log the verification only after successful verification.
2. Confirm customer authority and ownership for each account involved. Retrieve current facts necessary for the applicable prerequisite list.
3. Confirm that the customer authorizes opening the exact official account class. Confirm product eligibility and all relevant account terms before proceeding.
4. Only after all checks pass, use the normal banking account-opening tool with the verified customer identifier, correct account type, and exact confirmed account class. Do not expose internal tool mechanics to the customer.
5. For a savings account, ask separately whether the customer wants an opening deposit transferred now. A transfer requires a separate affirmative authorization and a confirmed amount.
6. Before a transfer, reconfirm source and destination ownership, available funds, amount, fees, limits, cutoffs, account identifiers, and recipient details. Use the business checking account that meets both the 30-day and $2,500 conditions.
7. If funding is deferred, explain the documented 30-day funding deadline and that the account will close if not funded in time. If a transfer fails, do not retry blindly; explain the failure and the available funding options.

## Final validation

Before responding, confirm that:

- Every customer requirement has been addressed as met, failed, or pending a specifically named missing term.
- Each product claim is supported by supplied documentation.
- A recommendation calls a product confirmed only when all material requirements are documented as met.
- Conditional candidates clearly state the material balance, fee, eligibility, or other term still needing confirmation.
- Promotions were active and used only as a ranking rule among products with no known failure.
- No account opening or transfer occurred without verification, authority, ownership, eligibility, current balance, fee/limit/cutoff, exact-account-class, and explicit confirmation checks.
- The final response reports only tool actions that actually succeeded.
