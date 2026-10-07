---
name: credit-card-rewards-discrepancy-review
description: Review posted credit-card rewards against a documented card reward plan, calculate expected whole-point earnings, identify discrepancies, and safely explain next steps. Use for inquiries about missing, incorrect, or unexpectedly low cash back/rewards.
---

# Credit Card Rewards Discrepancy Review

Use this Skill to review a customer's posted credit-card reward earnings. It calculates an audit only; it does not redeem points, change a balance, or apply a rewards adjustment.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Preconditions and safe handling

1. Identify the customer using a customer-provided account identifier, email address, user ID, or exact full name. Resolve ambiguous matches before proceeding.
2. Before retrieving, disclosing, altering, redeeming, or disputing account-specific rewards information, verify the customer by confirming two of the four identity fields (date of birth, email, phone number, and address). Obtain the current time and create the required verification log with all returned identity fields and the timestamp.
3. Confirm that the card account belongs to the verified customer and that the transaction belongs to that card/product. For a review-only calculation, available credit, balances, recipients, fees, cutoffs, and confirmation for a monetary transaction are not applicable. Do not treat a review as authorization to make an adjustment or redemption.
4. Use only posted/completed purchases. Do not calculate bonus eligibility from a merchant name alone when the posted merchant category is missing or disputed. Refunds, returns, fees, interest, insurance premiums, gift cards, and person-to-person payments must be excluded or marked for manual review when identifiable.
5. Never infer reward rates for a card that is not documented in the supplied policy. Ask for the card terms or route the matter for review instead.

If read-only records were already supplied by the task environment, use them only as evidence for the calculation. Do not let their presence substitute for required identity verification before making account-specific disclosures or any banking action.

## Reward rules represented by this Skill

- Database `points` on cash-back cards represent cash back at **1 point = $0.01** when redeemed as a statement or eligible checking credit.
- Calculate points as `floor(transaction_amount × reward_rate_as_decimal × 100)`. Always truncate fractional points; never round to nearest.
- For the Silver Rewards Card, documented posted transactions categorized as **Travel** or **Software** earn 4.0%; documented non-bonus purchases earn at least 1.0%. Merchant classification controls whether the enhanced rate applies.
- A discrepancy is `expected_points - recorded_points`. A positive result is a potential shortfall; a negative result is an apparent over-credit. Neither result by itself authorizes a change.

## Procedure

1. After completing applicable verification and account ownership checks, retrieve the card account and its transaction history using the ordinary banking tools.
2. Build a `reward_plan` from the documented card terms. Rates are expressed as percentage values, for example a base rate of `"1.0"` and a Travel bonus of `"4.0"`. Only include categories whose bonus rate is documented.
3. Normalize the relevant transactions into the input schema below and run:

   `python3 scripts/audit_rewards.py < input.json`

   The execution runtime sends the JSON object on standard input and receives the JSON result on standard output.
4. Read `audited_transactions` for individual findings and `totals.net_shortfall_points` for the net account impact across the reviewed set. `manual_review` records cannot support a definitive rate conclusion.
5. Explain the calculation in cash and points, including that points are worth one cent and fractional points are truncated. State which transactions match the documented plan and which require investigation.
6. If a potential shortfall, merchant-code issue, or unexplained result remains, collect the transaction date, merchant, amount, recorded rewards, expected rewards, and receipts if available. Use the normal rewards-discrepancy support procedure or a human transfer when the available tools cannot investigate or correct it. Do not claim an adjustment was made unless a banking tool confirms it.

## Script input schema

```json
{
  "reward_plan": {
    "card_type": "documented card name",
    "base_percent": "percentage",
    "bonus_percent_by_category": {"Category": "percentage"}
  },
  "transactions": [
    {
      "transaction_id": "optional identifier",
      "merchant_name": "optional merchant",
      "transaction_amount": "decimal dollars",
      "category": "posted category",
      "status": "COMPLETED or POSTED",
      "rewards_earned": "whole recorded points"
    }
  ]
}
```

The script emits:

- `ok`: whether input was structurally valid;
- `audited_transactions`: eligible posted transaction calculations with expected and recorded points, dollar equivalents, rate, and discrepancy;
- `manual_review`: excluded, unposted, malformed, or unsupported-category records and their reasons;
- `totals`: sums for auditable records, including net shortfall/over-credit; and
- `errors`: input-level errors, if any.

A category absent from `bonus_percent_by_category` receives `base_percent`; this is appropriate only when the supplied plan says non-bonus purchases earn the base rate. Exclusions should be omitted or sent with `review_reason` so they are not silently treated as ordinary purchases.

## Output validation

Before relying on a result, ensure `ok` is true, `errors` is empty, every transaction intended for review is either in `audited_transactions` or `manual_review`, and all expected point values are integers. Reconcile the sum of recorded points in the audit with the reviewed transaction records; do not reconcile it to an account-wide rewards balance unless the review period is complete and no unrelated activity exists.

When communicating results, distinguish a documented category/rate calculation from an unresolved merchant-classification decision. If verification has not been completed, ask for the needed identity fields rather than disclosing transaction-specific findings.
