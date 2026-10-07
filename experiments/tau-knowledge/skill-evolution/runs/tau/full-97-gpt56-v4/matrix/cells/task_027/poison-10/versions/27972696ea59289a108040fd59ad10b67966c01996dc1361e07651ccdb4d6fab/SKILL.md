---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit posted credit-card reward transactions against the documented Business Silver Rewards Card and Silver Rewards Card earning terms, including the Business Silver six-month double-cash-back promotion, merchant exclusions, and points-to-cash conversion. Use when a customer reports missing, incorrect, or confusing rewards.
---

# Credit-card rewards audit

Use this Skill to explain a rewards concern from account and transaction records without guessing from the account-level reward balance. Transaction-database `points` on the covered cash-back cards represent cash back at **100 points = $1.00**.

## Workflow

1. Identify the customer and retrieve their credit-card accounts and transaction history using the normal read-only banking tools. A rewards explanation based only on those read-only records does not itself require an account-changing action.
2. Build the JSON input described below from the returned records. Include the opening date for each card type being audited and use the current date only for context; eligibility is determined by each transaction date.
3. Run `scripts/audit_rewards.py`. It returns a per-transaction determination and a summary of shortfalls/overages only where the supplied terms establish an expected rate.
4. Review transactions with `disposition: "mismatch"` first. State the transaction date, merchant, amount, actual points/cash-back value, expected points/cash-back value, and point difference. Explain the applicable rate and why it applies.
5. Explain non-mismatches that could look surprising:
   - Business Silver qualifying travel/software normally earns 10%, or 20% during an eligible cardholder's first six months.
   - Business Silver excluded merchants earn the 1% standard rate; during the eligible double-cash-back period that is 2%.
   - After the Business promotional six-month window, qualifying travel/software returns to 10% and other purchases to 1%.
   - Silver Rewards qualifying travel/software earns 4%; this Skill does not infer an undocumented Silver base rate for other categories.
6. Do not use the account-level reward-points balance to prove a missing-reward amount: it can reflect prior credits or redemptions not present in the transaction list. Do not promise or perform a reward adjustment unless a separately authorized banking procedure/tool is available. If the normal support workflow cannot correct a confirmed mismatch, accurately say that the transaction needs a rewards review or transfer according to the available policy.

## Conversation guidance

Be transparent that merchant category coding and posting status control bonus eligibility. Only posted/completed purchase records are evaluated. Returns, refunds, non-purchase charges, missing fields, unsupported card products, and ambiguous duplicate card accounts are reported as not assessable rather than guessed.

When replying, lead with the conclusion in cash-back dollars as well as points, because these cards store cash back as points. Do not disclose unnecessary full account identifiers or unrelated personal information. If the customer asked only a broad question, proactively summarize the audited transactions that differ and invite them to identify any additional charge they want reviewed.

## Script interface

Run:

```text
python3 scripts/audit_rewards.py < input.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Input schema:

```json
{
  "as_of": "YYYY-MM-DD",
  "accounts": [
    {"card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "optional string",
      "credit_card_type": "Business Silver Rewards Card",
      "merchant_name": "Merchant",
      "transaction_amount": 12.34,
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": 247
    }
  ]
}
```

`as_of` is optional and is echoed only as context. Dates must be ISO dates; `transaction_amount` may be a JSON number or a dollar-formatted string; `rewards_earned` may be a number or a string such as `"247 points"`.

The output contains `evaluations`, with `expected_points` only where terms support a calculation, plus `summary`. A `mismatch` has a signed `point_difference` of `expected - actual`; a positive value is a shortfall. `cash_difference` is the same difference at $0.01 per point. `not_assessable` entries must not be represented to the customer as errors.

## Validation before relying on the result

Confirm that each assessed transaction has a completed/posted status, valid date, nonnegative amount, known card opening date, category, merchant, and recorded reward points. Confirm the reported calculation in two forms: `expected_points = round_half_up(amount × rate × 100)` and `cash value = points ÷ 100`. Ensure that a Business promotional transaction falls on or after its account-opening date and before the calendar date six months later; eligibility also requires that the account was opened from 2024-11-14 through 2025-11-14 inclusive.
