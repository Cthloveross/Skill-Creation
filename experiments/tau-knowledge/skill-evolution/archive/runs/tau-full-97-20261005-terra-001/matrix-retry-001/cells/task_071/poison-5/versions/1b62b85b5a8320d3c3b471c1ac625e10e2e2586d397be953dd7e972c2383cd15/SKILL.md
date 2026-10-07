---
name: business-account-recommendation-and-opening
version: 1.0.0
description: Recommend business checking and savings products from documented, current product facts and, only after explicit customer confirmation and eligibility checks, safely open the selected account and optionally fund a new savings account.
---

# Business Account Recommendation and Opening

Use this Skill when a customer wants a business checking account, a business savings account, or both, and has stated feature requirements or asks to open an account. It separates non-actionable recommendations from account-opening actions.

## Safety control for any banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A recommendation alone is not a banking action. Opening an account, transferring an opening deposit, or changing a setting is a banking action and must not occur until every applicable prerequisite is verified.

## Inputs to collect

1. Separate the request into checking and savings requirements. Capture measurable requirements such as daily mobile-deposit minimum, same-day ACH availability, APY, balance, fees, transfers, cash deposits, and access needs.
2. Obtain the current date when a dated promotion may affect ranking.
3. Use supplied product documentation to create product records with only documented facts. Do not infer an unlisted feature, fee, eligibility criterion, or limit.
4. Ask only for unresolved requirements that could change the recommendation. Do not make the customer compare products if their requirements already identify qualifying choices.
5. Before opening, collect or retrieve the customer identifier, verified identity status, authority, relevant owned accounts, account statuses, balances, tenure, account counts, and the exact official account class selected by the customer.

## Recommendation workflow

1. Turn each stated requirement into a testable condition. Treat an unstated preference as unknown rather than a requirement.
2. Evaluate each documented product against every stated condition. A product with a missing fact needed to prove a requirement is not a confirmed match.
3. If an active promotion applies to the requested product type, use it only to rank products that already satisfy every stated requirement. Check its start and end dates against the current date. Never use a promotion to override a requirement.
4. Present the highest-ranked confirmed product for each requested account type, followed by the exact supporting facts relevant to the customer. Mention material limits, fees, or conditions only when documented and relevant.
5. If no product can be confirmed, say which requirement lacks a qualifying documented product or which fact is missing. Ask a targeted clarification or offer a non-actionable alternative only when supported by documentation.
6. Do not open an account based solely on a recommendation. Obtain an explicit confirmation to open the selected, exact account class.

For deterministic matching, run:

```text
python scripts/rank_products.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. It performs no banking action.

### `rank_products.py` input schema

```json
{
  "as_of": "YYYY-MM-DD",
  "requirements": {
    "checking": {
      "minimums": {"mobile_deposit_daily_limit": 0},
      "equals": {"same_day_ach": true}
    },
    "savings": {
      "minimums": {},
      "equals": {"same_day_ach": true}
    }
  },
  "products": [
    {
      "name": "Official product name",
      "product_type": "checking",
      "features": {"mobile_deposit_daily_limit": 0, "same_day_ach": true}
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

`minimums` means the documented numeric feature must be at least the requested number. `equals` requires an exact value. Use integer cents for monetary values where fractional precision matters. Omit a constraint that the customer did not state. Promotions are optional.

The output contains each requested product type, ranked confirmed matches, rejected products with specific failed or missing conditions, and an active-promotion indicator. Use only `ranked_matches` as confirmed recommendations.

## Opening workflow

Perform this workflow only after the customer explicitly authorizes opening a particular account class.

### Business checking prerequisites

Confirm all of the following from reliable account and identity records:

- Customer identity is verified.
- The customer has at least one existing personal checking account with status `OPEN`.
- The customer does not exceed 6 business checking accounts.
- The customer has no accounts with status `CLOSED`.
- The customer's existing checking account has a balance of at least $500.
- The customer confirms the desired exact official business-checking `account_class`.

### Business savings prerequisites

Confirm all of the following from reliable account and identity records:

- Customer identity is verified.
- The customer has at least one business checking account with status `OPEN`.
- The customer has fewer than 4 existing business savings accounts.
- The customer has no accounts with negative balances.
- At least one existing business checking account has been open for at least 30 days.
- That business checking account has a current balance of at least $2,500.
- The customer confirms the desired exact official business-savings `account_class`, including its official suffix where applicable.

Evaluate these data-driven prerequisites with:

```text
python scripts/evaluate_opening_eligibility.py < eligibility.json
```

This script reads and writes JSON and never verifies identity, retrieves data, or initiates an action. It returns `eligible: true` only when each test supplied to it passes, `eligible: false` when a supplied test fails, and `eligible: null` when required evidence is missing.

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

Balances are integer cents. For a checking opening, provide `identity_verified`, `has_closed_accounts`, `current_business_checking_count`, and `open_personal_checking_balances`. For a savings opening, provide `identity_verified`, `current_business_savings_count`, `has_negative_balance`, and `business_checking_accounts`. Extra fields are ignored.

### Action sequence

1. Verify identity using the approved verification procedure and record it through the normal verification tool when successful.
2. Confirm authority and ownership for every affected account. Retrieve current account facts needed for the applicable prerequisite list and evaluate them.
3. Confirm the exact official account class and the customer's authorization to open it. A product recommendation is not this confirmation.
4. Unlock the documented account-opening agent tool, then call it using the verified customer identifier, the appropriate account type (`checking` or `savings`), and the exact confirmed account class. Do not expose internal tool mechanics to the customer.
5. For a new savings account, retain the returned new account identifier. Ask whether the customer wants to transfer the opening deposit now from the qualifying open business checking account.
6. Transfer funds only if the customer expressly authorizes it and confirms the amount. Reconfirm source ownership, available funds, applicable limits, fees, cutoffs, destination, and source/destination account identifiers. Use the qualifying checking account that satisfies both the 30-day and $2,500 requirements.
7. If the customer declines immediate funding, explain the documented 30-day funding deadline and that internal transfer or external deposit are available; state that the account will be closed if it is not funded in that period.
8. If an authorized funding transfer fails, do not retry blindly. Explain the failure and the same 30-day funding options.

## Response and validation

For a recommendation response, include the recommended checking and/or savings product, the facts that satisfy the stated requirements, and any needed next confirmation. Do not claim eligibility to open until opening prerequisites are verified.

For an opening response, confirm only actions that actually returned success. State whether the account was opened, whether any authorized funding transfer succeeded, and any remaining customer action. Never invent an account identifier, balance, confirmation, or transfer outcome.

Before sending the response, validate that:

- Every stated requirement is addressed.
- Every product claim appears in current supplied documentation.
- Promotion ordering was applied only while active and only among qualifying products.
- No banking action occurred without identity, authority, ownership, eligibility, balance, fee/limit/cutoff, detail, and confirmation checks.
- No savings funding transfer occurred without explicit authorization and amount.
- Unverified facts and unavailable actions are identified plainly.
