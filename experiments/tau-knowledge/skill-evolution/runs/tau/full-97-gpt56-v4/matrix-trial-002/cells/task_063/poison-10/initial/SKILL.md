---
name: savings-card-yield-recommendation
version: 1.0.0
description: Compare a personal savings account and credit-card combination when a customer wants to maximize savings interest, has account-delivery preferences, and may later want to apply or open/fund accounts. Use for recommendations and for safely preparing—not automatically performing—related banking actions.
---

# Savings and card yield recommendation

Use this Skill to produce a transparent, evidence-based recommendation for a savings account plus a credit card that may contribute an APY bonus. It distinguishes a product recommendation from an application, account opening, or transfer. A recommendation does not open accounts, submit a credit application, change statement delivery, or move money.

## Inputs to collect

Collect only the facts needed for the recommendation:

- Amount expected to remain in savings and whether it may fluctuate.
- Savings-product requirements: opening and ongoing minimums, APY tiers, compounding/crediting treatment, statement-delivery availability and fee, and applicable product fees.
- Customer constraints, such as mailed-paper-statement requirement, direct-deposit status, and any required account features.
- Credit-card requirements: stated credit-score range, subscription requirements, annual fee, whether a credit review is required, and the APY bonus for the particular savings product.
- Whether bonuses stack, and whether a checking-account pairing is specifically eligible for a boost.
- If the customer wants to act: authenticated identity, account ownership, eligibility, source account, available balance, all relevant fees/limits/cutoffs, and explicit confirmation.

Do not treat a customer statement that they hold an account, have a score, or meet a threshold as verified account or underwriting eligibility. Describe any result based on such information as estimated or conditional.

## Method

1. **Separate eligibility from preference.** Eliminate options that fail a hard preference (for example, paper statements are unavailable or prohibited) or a known product eligibility condition. List unknown conditions rather than assuming them are met.
2. **Find the applicable savings tier.** Use the balance-tier rule documented for that savings account. Do not assume tiered pricing is marginal: first determine from the product disclosure whether the tier rate applies to the whole balance or only to a balance slice.
3. **Apply bonuses correctly.** Add only bonuses whose qualifying condition is actually active. If card bonuses do not stack, use only the highest applicable active card bonus. Do not infer a linked-checking boost merely because a customer has a checking account; the exact pairing must qualify.
4. **Estimate one-year earnings.** When an account advertises APY and the balance is assumed constant for a full year, estimate annual interest as `balance × total APY`. APY already expresses an annual yield, so do not compound it again. State that actual credited interest varies with daily balances, timing, qualification changes, rate changes, and the account's posting schedule.
5. **Compare like-for-like value.** If card annual fees are relevant to the requested comparison, show both gross savings interest and interest less annual card fee. Do not claim that a card's other rewards or credit cost are captured by this savings-yield estimate.
6. **Explain the recommendation and alternatives.** Give the qualifying APY components, estimated dollar result, statement-delivery result, important minimums, and why excluded alternatives fail. If an optional setup (such as direct deposit) would improve APY, present it separately and only if the customer can actually qualify.

Use `scripts/compare_options.py` for repeatable ranking. Supply facts extracted from the current task's authoritative product materials; its input deliberately contains the current catalog and does not embed product-specific facts.

## Runnable calculator

The script reads one JSON object from standard input and writes one JSON object to standard output.

Minimal schema:

```json
{
  "balance": "8000.00",
  "profile": {
    "credit_score": 700,
    "credit_score_confirmed": false,
    "paper_statements_required": true,
    "direct_deposit_active": false,
    "subscriptions": []
  },
  "savings_options": [
    {
      "name": "Account name",
      "opening_minimum": "0",
      "ongoing_minimum": "0",
      "paper_statements_available": true,
      "paper_statement_monthly_fee": "0",
      "tiers": [{"minimum_balance": "0", "apy_percent": "3.0"}],
      "direct_deposit_bonus_percent": "0",
      "other_active_bonus_percent": "0"
    }
  ],
  "card_options": [
    {
      "name": "Card name",
      "minimum_credit_score": 0,
      "credit_review_required": true,
      "annual_fee": "0",
      "subscription_required": null,
      "savings_apy_bonus_percent": {"Account name": "0"}
    }
  ]
}
```

Example invocation by an executor:

```sh
python3 scripts/compare_options.py < comparison_input.json
```

For every result, check that `status` is `ok`, that at least one `ranked_combinations` entry exists, that the chosen entry has `paper_requirement_met: true` when required, and that its `card_bonus_percent` is the single highest applicable card bonus rather than a sum. Review `warnings` before communicating a recommendation.

## Safe transition from advice to banking action

Do not initiate an action from the calculator result. First ask the customer to choose the precise product(s) and explicitly authorize the requested action.

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a personal savings-account opening, additionally verify all documented prerequisites: identity verification; at least one active checking account; required checking tenure; fewer than the permitted maximum personal savings accounts; no collections or negative balances; the exact official savings account class; and the required opening deposit and funding deadline. Confirm the customer’s source checking account and available balance before an internal funding transfer.

If identity verification is required, obtain and match two of the permitted identity fields against the customer record, retrieve the current time, and create the required verification audit record before proceeding. Use only normal declared banking tools. If the runtime lacks a tool for a requested application, statement preference, or account action, explain the limitation and give the documented next step; never claim that it was completed.

For a credit-card application, verify applicable score, subscription, identity, authority, and disclosures; obtain consent where a credit check is required. Meeting a published minimum is not an approval promise.

Use `scripts/check_action_prerequisites.py` as a local completeness check before an action. It only reports missing data and never performs a bank action.
