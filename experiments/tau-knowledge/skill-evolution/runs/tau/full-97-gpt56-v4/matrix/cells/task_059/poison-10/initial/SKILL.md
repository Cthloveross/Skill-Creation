---
name: fee-aware-savings-and-card-comparison
description: Compare a customer's savings-account and credit-card options for an estimated one-year net return when account/card terms, expected balances, spending, known eligibility, and fee preferences are supplied. Use for product advice only; it does not open, modify, or link accounts.
---

# Fee-Aware Savings and Card Comparison

Use this Skill to produce a transparent, conservative product recommendation from documented product terms and the customer's stated goals. It is appropriate for a customer seeking to maximize estimated interest plus applicable rewards minus documented fees, especially when eligibility or fee information is incomplete.

## Scope and safety

This is an advisory workflow, not a banking action. Do not open an account, submit a credit-card application, link products, redeem rewards, or change settings merely because the comparison identifies a preferred option.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an application or account-opening request, first confirm the customer wishes to proceed and then collect or direct the customer to provide the required application information. Never claim approval, an exact credit limit, or that a benefit is active before verification and the normal banking process.

## Method

1. Extract only terms documented for the candidate products: savings APY, required opening/ongoing balance, maintenance and other relevant fees, card annual fee, any subscription cost, ordinary-purchase reward rate, stated eligibility requirements, and any explicitly documented product-link bonus.
2. Capture the customer's initial deposit, expected monthly card spend, expected spending categories, payment behavior, existing products, known score/eligibility, and fee preferences. Treat missing eligibility facts as **unknown**, not satisfied.
3. Apply exclusions the customer explicitly requests. Exclude candidates with undocumented fees when the customer asks for clearly documented fees.
4. For rewards, use an ordinary/known eligible rate only when the customer's spending category is supported. Do not assume category bonuses, merchant classification, introductory bonuses, or fee waivers.
5. For savings bonuses, use only bonuses documented for that exact savings product and confirmed product relationship. If several same-type bonuses are available and policy says only the highest applies, use the highest rather than adding them. Do not infer a linked-checking boost from a checking account unless the exact pairing and boost are documented.
6. Estimate the one-year amount using the supplied normalized terms. Run `scripts/compare_products.py` for consistent arithmetic and ranking.
7. Explain both the recommendation and uncertainty: show estimated interest, rewards, fees, net amount, eligibility status, assumptions, and why potentially higher-return alternatives were excluded or remain conditional.
8. When the customer does not know a required credit score, recommend the qualifying path with the lowest documented threshold among otherwise suitable, documented-fee options only as a conditional recommendation. Clearly state that approval remains subject to underwriting.

## Calculator interface

Run the script with JSON on stdin (or through `run_skill_script`) using this schema:

```json
{
  "starting_savings": "number",
  "monthly_card_spend": "number",
  "months": "integer, defaults to 12",
  "preferences": {
    "avoid_undocumented_fees": "boolean",
    "avoid_subscription": "boolean"
  },
  "cards": [
    {
      "name": "string",
      "annual_fee": "number",
      "monthly_subscription_fee": "number",
      "fee_documented": "boolean",
      "eligibility": "eligible | unknown | ineligible",
      "ordinary_reward_rate_percent": "number",
      "savings_apy_bonus_percent": "number, defaults to 0",
      "excluded": "boolean, optional"
    }
  ],
  "savings": [
    {
      "name": "string",
      "base_apy_percent": "number",
      "monthly_maintenance_fee": "number",
      "eligibility": "eligible | unknown | ineligible",
      "linked_checking_apy_bonus_percent": "number, defaults to 0",
      "linked_boost_established": "boolean, defaults to false"
    }
  ]
}
```

All monetary inputs are in dollars. Reward rates must already be normalized to dollar value (for example, convert point programs using their documented redemption value before supplying a rate). Supply a card APY bonus only when it applies to the particular savings product. The calculator treats APY as the annual yield on the supplied balance; it does not invent daily-balance changes, taxes, interest on card balances, or undocumented fees.

The script emits a JSON object with every combination, excluded combinations and reasons, the sorted viable combinations, and a `recommended` combination. `recommended` may have `eligibility: "unknown"`; word that result conditionally rather than as an approval prediction.

Example invocation pattern:

```sh
python3 scripts/compare_products.py < comparison_input.json
```

## Output quality check

Before presenting advice, verify that:

- each amount uses the customer's actual stated horizon and spending estimate;
- annual card fees and monthly subscription/maintenance fees were subtracted for the whole comparison period;
- every excluded option has a stated reason;
- unknown credit score, subscription status, reward category, or linked-account eligibility is visibly labeled as an assumption or condition;
- the response does not turn advice into an account-opening action; and
- no APR cost is included when the customer says they will pay the statement balance in full, while reminding them that carrying a balance would change the comparison.

If terms conflict, are missing, or do not establish a required bonus, do not resolve the conflict by guessing. Use the less favorable documented interpretation where appropriate, state the limitation, and invite the customer to provide or verify the missing product disclosure.
