---
name: savings-card-net-yield-advisor
description: Compare a personal savings account and credit-card combination when a customer wants to maximize one-year savings interest minus annual fees. Use for product advice and transparent calculations; do not use it to open accounts, apply for cards, or move funds without completing the applicable banking procedure.
---

# Savings and credit-card net-yield comparison

Use this Skill to recommend the best documented savings-account and credit-card pairing for a stated deposit amount and one-year objective. It is designed for an assumed constant balance, daily compounding, and a stated objective of **savings interest less annual fees**.

## Scope and assumptions

1. Treat an APY as an effective annual yield. For a constant balance held for 365 days, daily compounding derived from that APY produces one year's stated APY. The calculation is:
   - `daily_rate = (1 + APY / 100)^(1/365) - 1`
   - `interest = deposit * ((1 + daily_rate)^365 - 1)`
   - `net = interest - selected_card_annual_fee - applicable_account_annual_fees`
2. Add compatible bonus APY percentages to the applicable base-tier APY only when the product documentation says they stack.
3. Credit-card bonuses do not stack with each other: use only the highest applicable card bonus. Likewise, use only the highest applicable linked-checking boost if more than one qualifying checking account is present. A qualifying checking boost may stack with the selected card bonus and a documented relationship bonus.
4. Never infer a checking boost merely because the customer has a checking account. Confirm that the exact checking/savings pairing is listed in the documentation; otherwise use a 0% checking boost.
5. Screen out accounts whose documented ongoing balance requirement the customer cannot meet when the comparison is intended to identify a suitable account. If the customer expressly wants to compare below-minimum accounts, disclose the requirement and include any documented maintenance fee separately rather than silently treating the account as unrestricted.
6. Do not count sign-up bonuses, points, cash back, spending rewards, promotional statement credits, or unverified fee waivers unless the customer explicitly expands the objective and provides the qualifying spending/activity assumptions. Do not treat an illustrative example as a product term.
7. A recommendation is not an approval. State unresolved eligibility requirements, such as identity/income information, credit score, subscription, account status, or product availability.

## Required data-gathering and comparison workflow

1. Restate the objective, deposit amount, horizon, and constant-balance assumption. Ask a focused clarifying question if any of these is missing.
2. From the supplied product documentation, create a small normalized candidate list containing:
   - savings account official name;
   - opening and ongoing minimums;
   - APY tiers and their balance thresholds;
   - documented annual/monthly maintenance fees relevant to the proposed balance;
   - card annual fee and applicable bonus APY by savings account;
   - documented relationship bonus and exact qualifying checking/savings boost, if any;
   - card eligibility prerequisites relevant to applying.
3. Confirm whether the customer has other active eligible cards or checking accounts. If known, use only the highest applicable bonus within each respective category. If unknown and it can change the outcome, state that limitation rather than claiming a guaranteed personalized rate.
4. Run `scripts/compare_net_yield.py` with only facts supported by the current documentation. Do not hardcode a customer identity, current-instance product answer, or expected calculation result into the script or its input template.
5. Check that the winning account can receive the proposed deposit under its opening and ongoing terms, and that its credited APY components were applied exactly once.
6. Give a concise recommendation that shows: selected savings account and card, base APY/tier, each included bonus and why it applies, effective APY, projected gross interest, annual fees deducted, projected one-year net, material exclusions, and any conditions that remain to be confirmed.
7. Offer to explain terms or begin the appropriate application/opening process. Do not imply that advice itself opened an account or submitted a card application.

## Calculator

Run `scripts/compare_net_yield.py` with JSON on stdin. It emits JSON on stdout.

### Input schema

```json
{
  "deposit": 0,
  "days": 365,
  "checking_account": "optional exact checking name",
  "require_ongoing_minimum": true,
  "fixed_annual_fees": 0,
  "savings": [
    {
      "name": "official savings name",
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "annual_maintenance_fee_below_minimum": 0,
      "extra_apy_percent": 0,
      "tiers": [{"minimum_balance": 0, "apy_percent": 0}]
    }
  ],
  "cards": [
    {
      "name": "official card name",
      "annual_fee": 0,
      "bonuses": [{"savings": "official savings name", "apy_percent": 0}]
    }
  ],
  "checking_boosts": [
    {"checking": "official checking name", "savings": "official savings name", "apy_percent": 0}
  ],
  "existing_card_bonuses": [
    {"savings": "official savings name", "apy_percent": 0, "source": "optional label"}
  ]
}
```

`tiers` must contain the whole-balance APY for every supported threshold, including a zero threshold. `extra_apy_percent` is for a documented savings-level bonus that stacks independently. Omit unknown bonuses rather than estimating them. `fixed_annual_fees` is optional and should be used only for documented fees that truly belong in the customer's stated objective.

### Output interpretation and validation

The output contains `ranked_combinations`, highest net first, plus `excluded_savings` and `warnings`.

Before relying on a result, verify that:

- every candidate has an explicit tier at or below the deposit;
- the selected card's bonus is mapped to the selected savings account;
- an absent checking-pair record resulted in a zero checking boost;
- only one card bonus and one checking boost were included;
- annual fees are actually annual (convert a documented monthly fee to annual before input);
- account/card names, amounts, APYs, and minimums match the current documents; and
- all exclusions and warnings are addressed in the customer-facing explanation.

The script is deterministic and advisory only. It does not access bank records, establish eligibility, apply for a card, open an account, or transfer funds.

## Banking-action gate

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

If the customer elects to act after receiving the comparison:

- Authenticate the customer and confirm identity verification before accessing account-specific records or proceeding.
- For a savings-account opening, confirm the customer has an active qualifying checking account, any required tenure, fewer than the permitted maximum personal savings accounts, no disqualifying collections/negative balances, the exact official savings account class, and the required opening deposit. Obtain explicit confirmation before opening. If immediate funding is requested, separately verify source-account ownership, available funds, destination, amount, fee/limit/cutoff details, and transfer confirmation.
- For a card application, verify the customer is authorized, confirm all documented eligibility and required application information, present applicable fees and APR terms, and obtain explicit confirmation before submitting an application. Do not represent approval as certain.
- If required facts, authorization, or a documented tool/process are unavailable, do not perform the action. Explain what is needed or route through the approved process.
