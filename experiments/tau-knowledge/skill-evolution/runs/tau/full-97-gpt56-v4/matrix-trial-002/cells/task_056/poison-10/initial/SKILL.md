---
name: business-checking-account-recommendation
description: Recommend a business checking account from supplied product evidence when a customer describes operating needs or non-negotiable fee constraints. Use for informational comparisons; do not use it to open, modify, or transfer funds from an account.
---

# Business Checking Account Recommendation

## Scope and safety

Use this workflow for an informational product recommendation only. A recommendation does not open an account or change the customer's existing account. Do not claim eligibility, availability, approval, or that a product has a feature unless it is supported by the supplied evidence.

If the customer asks to open or change an account, treat that as a separate banking action. Before that action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Use only the declared banking tools and obtain any required confirmation before executing the action.

## Method

1. Extract the customer's explicit requirements. Mark words such as “must,” “need,” and “non-negotiable” as hard constraints. Treat preferences such as “more features” as ranking criteria unless quantified.
2. Build a fact table only from the supplied product evidence. Record both benefits and material tradeoffs, including recurring fees, waiver conditions, transaction allotments, overdraft policy, transfer fees, limits, and eligibility facts. Do not infer undocumented policies from a product's name or from another account tier.
3. Exclude every product that is known not to meet a hard constraint. A product with an unknown value for a hard constraint is not a proven match and must not be presented as satisfying it.
4. Optionally run `scripts/rank_accounts.py` with a normalized fact table to make filtering and preference ranking repeatable. The script is advisory; verify that its input facts accurately reflect the supplied evidence.
5. State the recommendation first, then explain why it meets each hard requirement and the concrete feature improvements relevant to the customer's stated need.
6. Clearly disclose material tradeoffs. For example, disclose a monthly fee and its documented waiver condition alongside a recommendation, rather than implying that the account is free.
7. When an important requested capability is not documented (for example, cash-deposit availability, branch access, payroll integration, or merchant integrations), say it was not established by the available information. Ask a focused follow-up only if it could change the recommendation.
8. End with an appropriate next step: offer to compare the recommended product against the current account in more detail, or—if the customer wants to proceed—explain that opening requires a separate eligibility and verification process. Do not perform that process within this informational response.

## Recommended response structure

- **Recommendation:** name the single best proven match.
- **Why it fits:** tie each point to a stated need, especially hard constraints.
- **Key features:** list only documented relevant features and quantitative limits.
- **Tradeoffs:** state documented recurring fees, waiver thresholds, and relevant per-use fees.
- **Unknowns / next step:** identify unverified requested capabilities and invite the customer to provide volume or workflow details if needed.

For a customer who says zero overdraft fees are non-negotiable, explicitly distinguish a documented no-overdraft-fee policy from a product merely having no monthly fee. Do not recommend an account documented to charge overdraft fees.

## Ranking helper

`scripts/rank_accounts.py` reads JSON from standard input and writes JSON to standard output.

Input schema:

```json
{
  "requirements": {
    "must_equal": {"overdraft_fee": 0},
    "at_least": {"included_transactions": 100},
    "prefer_at_least": {"mobile_deposit_daily_limit": 10000},
    "prefer_true": ["cashback", "multiple_debit_cards"]
  },
  "accounts": [
    {
      "name": "Account name from supplied evidence",
      "features": {
        "overdraft_fee": 0,
        "included_transactions": 0,
        "mobile_deposit_daily_limit": 0,
        "cashback": false,
        "multiple_debit_cards": false
      }
    }
  ]
}
```

All fields are optional except `accounts` and each account's `name`. Use `must_equal` for exact hard constraints, `at_least` for numerical hard minimums, and the `prefer_*` sections only for non-binding ranking. Omit facts that are not documented; do not substitute guessed values. The output separates `eligible` accounts from `excluded` accounts and gives reasons for exclusion. An empty `eligible` list means no supplied product is a proven match, not that the requirement can be waived.

Example runnable call:

```sh
python3 scripts/rank_accounts.py <<'JSON'
{"requirements":{"must_equal":{"overdraft_fee":0}},"accounts":[{"name":"Example","features":{"overdraft_fee":0}}]}
JSON
```

Validate before relying on the result: every hard constraint should appear in the account evidence and every disclosed fee or limit in the customer response should match the evidence. The helper never creates a banking action or makes a product available to the customer.
