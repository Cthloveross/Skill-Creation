---
name: banking-product-combination-advisor
description: Compare personal savings-account and credit-card combinations for a customer's stated balance, spending, payment behavior, eligibility, and existing products. Use for a recommendation or explanation of projected one-year interest, rewards, and fees; use the action workflow only when the customer asks to open or fund an account.
---

# Banking Product Combination Advisor

Provide a transparent, customer-specific comparison of savings accounts and credit cards without treating an estimate as a guaranteed return. This Skill is for advice first; it must not open, fund, alter, or apply for any account unless the customer explicitly requests that action and all operational prerequisites have been verified.

## Required facts to collect or confirm

1. Savings amount, intended holding period, expected balance changes, and whether it meets each account's opening and ongoing balance requirements.
2. Expected card spending, principal categories, expected payment behavior, and foreign-use needs.
3. Product eligibility, including disclosed credit-score and subscription requirements. Do not infer an undisclosed score or eligibility.
4. Existing linked checking accounts and cards, plus the applicable bonus and pairing rules.
5. Annual, monthly, transaction, and conditional fees. Evaluate a fee only when its triggering condition is expected to occur.
6. Whether promotional terms are both applicable and still within their documented offer window. Obtain the current time when timing matters.

If a material fact is missing, either ask a focused clarification or state the assumption and show how it affects the result. Exclude unavailable products from the recommendation, while briefly explaining why. Do not assume that a promotional bonus will be earned without confirming every condition.

## Comparison method

1. Build a short candidate list from the supplied product documentation. Record source terms for base APY, tier thresholds, bonuses, cash-back/reward rates, annual fee, and maintenance fees.
2. Determine the applicable savings APY:
   - Select the balance tier based on the projected balance.
   - Apply a qualifying linked-checking boost only for a documented eligible pairing.
   - For multiple qualifying credit-card bonuses, apply only the highest bonus when the policy says card bonuses do not stack.
   - Add bonuses from distinct categories only where documentation explicitly permits them to stack.
   - Respect any product-specific benefit that changes a minimum balance or withdrawal allowance.
3. Project one year of savings return as `balance × applicable_APY`, then subtract expected maintenance and other applicable account fees. APY already represents annual yield; do not compound an APY again for a one-year estimate.
4. Project one year of card return as `annual eligible spend × applicable reward rate − annual fee − expected transaction fees`. For a spending range, calculate low and high results rather than inventing a midpoint. Do not include interest charges when the customer expects to pay each statement balance in full, but explain that carrying a balance changes the comparison.
5. Combine the selected savings return and card return for each compatible combination. Use `scripts/project_returns.py` for repeatable arithmetic where helpful.
6. Present the best eligible combination, runner-up(s) when useful, the estimated annual net result, and the assumptions that drive it. Explain why seemingly higher-rate products are excluded (for example, unavailable subscription, balance-triggered fee, or annual fee exceeding rewards).

Use the reward representation documented for the relevant card. If a system stores cash-back rewards as points, convert only using the documented redemption value and distinguish true points programs from cash back.

## Customer-facing response structure

- Give a concise recommendation first.
- Show a small calculation table: savings APY/interest/fees/net; card spend/rewards/fees/net; combined estimated net.
- Name key conditions: balance must remain at the assumed level, qualification must continue, posted eligible purchases count, and returns/refunds can reverse rewards.
- State unavailable or uncertain alternatives without presenting them as selectable.
- Offer to proceed only after the customer chooses a product. A recommendation is not account-opening consent.

## Action workflow: opening and funding a personal savings account

Use this workflow only after the customer explicitly selects the account and requests account opening. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a personal savings account, additionally verify all documented opening conditions before opening: identity is verified, the customer has an active qualifying checking account with required tenure, the customer is below the personal-savings-account limit, and there are no collections or negative balances. Confirm the exact official savings `account_class` name and required opening deposit.

After these checks and explicit selection:

1. Open the account through the documented normal banking tool using the authenticated customer's ID, `account_type: "savings"`, and the exact full official account class.
2. Ask whether the customer authorizes an immediate transfer of the required opening deposit from a specified eligible checking account. Do not transfer based on the earlier recommendation alone.
3. If authorized, re-verify account ownership, available balance, amount, fees, limits, recipient/destination account, cutoff, and confirmation requirement, then use the declared normal transfer tool.
4. If funding is declined, communicate the documented funding deadline and closure consequence.
5. Report the actual tool result and funding status. Never claim success without a successful tool result, and never retry an operation reported as unknown.

If identity, authority, eligibility, explicit consent, tool availability, or a required account detail is absent, do not perform the action. Explain the missing prerequisite or ask the narrow question needed to proceed.

## Calculator

`scripts/project_returns.py` reads JSON from standard input and writes JSON to standard output. It performs arithmetic only; it does not verify eligibility, retrieve terms, or initiate banking actions.

Input schema:

```json
{
  "savings_candidates": [
    {
      "id": "optional-label",
      "balance": "decimal dollars",
      "base_apy_percent": "decimal percent",
      "checking_bonus_apy_percent": "decimal percent",
      "card_bonus_apy_percents": ["decimal percent"],
      "other_bonus_apy_percent": "decimal percent",
      "annual_fees": "decimal dollars",
      "card_bonus_mode": "highest|sum"
    }
  ],
  "card_candidates": [
    {
      "id": "optional-label",
      "monthly_spend_low": "decimal dollars",
      "monthly_spend_high": "decimal dollars",
      "reward_rate_percent": "decimal percent",
      "annual_fee": "decimal dollars",
      "expected_other_annual_fees": "decimal dollars"
    }
  ]
}
```

All monetary fields must be nonnegative decimal strings or JSON numbers. Omitted optional fee and bonus fields default to zero; `card_bonus_mode` defaults to `highest`. The output includes savings and card one-year projections plus validation errors. Use only candidates already determined to be eligible and compatible.

Example invocation (values are placeholders, not product terms):

```sh
python3 scripts/project_returns.py <<'JSON'
{"savings_candidates":[{"id":"savings-a","balance":"5000","base_apy_percent":"4","card_bonus_apy_percents":["0.2","0.1"]}],"card_candidates":[{"id":"card-a","monthly_spend_low":"100","monthly_spend_high":"200","reward_rate_percent":"1","annual_fee":"0"}]}
JSON
```

Validate output before using it: confirm `errors` is empty, the selected tier and bonuses were determined from documentation rather than the script, savings `net_return` equals interest minus entered fees, and card low/high net return tracks the entered spending range.
