---
name: account-recommendation-intake
version: 1.0.0
description: Recommend checking and savings account options from supplied product terms and stated customer preferences, especially travel costs, balance thresholds, and withdrawal frequency. Use for informational account selection; do not use it to open, fund, transfer, or otherwise change an account.
---

# Account Recommendation Intake

Use this Skill to turn a customer's stated needs into a transparent, evidence-based shortlist. It is designed for product recommendations, not financial advice or account actions. Read the current task's product records and customer statements at runtime; do not assume that product terms in a prior task remain current.

## Safety boundary

A recommendation is not an account-opening authorization. Do not open an account, transfer an opening deposit, link products, alter an account, or imply that an account was opened merely because the customer says they will choose a recommendation. First obtain a specific account selection and then follow the applicable account-opening workflow using only the normal banking tools available in the current runtime.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an eventual personal checking opening, verify identity, adulthood, existing checking-account count, recent checking closures, and the exact official account class before opening. For an eventual personal savings opening, verify identity, an active qualifying checking account and its tenure, savings-account count, account standing (including collections and negative balances), the exact official account class, and any required opening deposit. Do not try to infer these facts from a recommendation conversation. If the relevant action tool is not declared in the runtime, explain that you cannot perform the opening here rather than attempting a substitute action.

## Method

1. **Separate products and needs.** Treat checking and savings as separate recommendations. Extract only facts actually stated by the customer, including:
   - checking balance they can maintain, travel destinations/frequency, foreign-purchase needs, ATM usage, and tolerance for maintenance fees;
   - savings balance, expected *maximum* monthly withdrawal count, opening-deposit ability, and whether avoiding withdrawal fees or maximizing yield is more important.
2. **Use the authoritative supplied terms.** For each product, retain the source record and evaluate conditions rather than presenting a benefit as unconditional. Examples include fee-waiver thresholds, eligibility requirements, transaction limits, rebate caps, and third-party charges.
3. **Screen checking options.** A travel-oriented option should be evaluated for foreign transaction fees, the bank's foreign ATM fee, ATM-operator-fee rebate cap and posting conditions, monthly maintenance fee, and balance needed to waive it. Distinguish an operator surcharge from a bank fee and state that a rebate is capped rather than guaranteed.
4. **Screen savings options.** Compare the customer's maximum expected monthly withdrawals to the product's free or permitted withdrawal count. Interpret a documented `-1` withdrawal limit only when the supplied terms define it as unlimited. If use could exceed the free allowance, do not claim the account is fee-free; identify the documented excess fee or say that the excess fee is not supplied. Also disclose opening and ongoing balance requirements and any maintenance fee conditions.
5. **Rank with stated priorities.** Prefer options that satisfy the required conditions and fit the customer’s stated balance. A zero-fee claim requires supporting terms. If crucial data is absent (for example, the savings balance or a product's excess-withdrawal fee), give a conditional recommendation or ask one focused question instead of inventing a comparison.
6. **Respond plainly.** Name the recommended option(s), why each fits, material limitations, and any assumption. Cite or identify the supplied product source when the response format permits. Do not promise rebates, APY, eligibility, account approval, or future policy terms.
7. **Only after a customer chooses a specific product**, transition to the applicable opening workflow and complete all safety checks above. If they do not choose one, leave the outcome as an informational recommendation.

## Deterministic helper

`scripts/recommend_accounts.py` ranks caller-supplied normalized product records. It never contains a product catalog, customer identifier, or task-specific answer.

### Input JSON schema

```json
{
  "preferences": {
    "checking_balance": 0,
    "international_travel": true,
    "requires_zero_foreign_transaction_fee": true,
    "needs_atm_rebates": true,
    "savings_withdrawals_per_month": 0,
    "requires_no_savings_withdrawal_fee": true
  },
  "checking_options": [
    {
      "name": "Official checking product name",
      "foreign_transaction_fee_percent": 0,
      "foreign_atm_bank_fee": 0,
      "atm_rebate_monthly": 0,
      "monthly_fee": 0,
      "fee_waiver_minimum_daily_balance": 0,
      "source": "Supplied product record"
    }
  ],
  "savings_options": [
    {
      "name": "Official savings product name",
      "opening_deposit_minimum": 0,
      "ongoing_minimum_balance": 0,
      "monthly_fee_below_minimum": 0,
      "free_withdrawals_per_month": 0,
      "excess_withdrawal_fee": 0,
      "source": "Supplied product record"
    }
  ]
}
```

All amounts must be numbers in the same currency. Omit an unknown field rather than using a guessed value. `free_withdrawals_per_month` may be `-1` only when the supplied product terms explicitly define it as unlimited. `savings_withdrawals_per_month` should be the customer’s expected maximum, not an average.

### Output JSON schema

The helper emits:

```json
{
  "checking": [{"name": "...", "score": 0, "fit": true, "reasons": [], "cautions": [], "source": "..."}],
  "savings": [{"name": "...", "score": 0, "fit": true, "reasons": [], "cautions": [], "source": "..."}],
  "missing_information": []
}
```

`fit` means that no supplied hard preference conflicts with a known term. It is not an eligibility or approval determination. Scores are only stable sorting aids; present the reasons and cautions, not a score, to the customer.

### Runnable call

```sh
python3 scripts/recommend_accounts.py < request.json > recommendation.json
```

Before relying on the result, verify that each offered product has an official name and a supplied source, that no unknown value was represented as zero, that the savings withdrawal estimate uses the high end of the customer’s range, and that all customer-facing claims appear in the returned reasons or cautions. If the helper reports missing information, ask only the question needed to resolve it or make the recommendation conditional.
