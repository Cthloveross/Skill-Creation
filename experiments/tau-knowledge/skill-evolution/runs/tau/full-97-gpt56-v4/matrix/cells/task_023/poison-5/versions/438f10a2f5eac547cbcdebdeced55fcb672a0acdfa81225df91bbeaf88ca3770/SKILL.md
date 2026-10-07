---
name: platinum-rewards-annual-fee-rebate-review
description: Review whether a Platinum Rewards Card cardmember-year meets the annual-fee rebate spending condition. Use when a customer asks whether they qualify for, earned, or should receive the rebate and card account and transaction data can be read.
---

# Platinum Rewards annual-fee rebate review

Use this Skill to make a read-only, evidence-based determination. It calculates the most recently completed 12-window cardmember year, using anniversary windows based on the account-opening date rather than calendar or statement months.

## Policy applied

For this card, the spend requirement is **$7,500 in net eligible purchases in every one of 12 monthly windows**. Each window starts on the monthly anniversary of the opening date and ends the day before the next anniversary. Transactions count by posting date. A single deficient window disqualifies that cardmember year; there is no prorated rebate. The rebate amount is **$150**.

Eligible amounts are net posted purchases, including authorized-user, virtual-card, and international purchases. Do not count fees, interest, adjustments other than purchase credits/returns, cash advances/cash equivalents, balance transfers, person-to-person funding transfers, or unresolved disputes. A return, refund, or purchase credit reduces the window in which it posts.

The first fee-waived promotional year is not rebate-eligible. A customer who otherwise qualifies receives the rebate as a statement credit after the annual fee for that cardmember year is billed. Closing or product-changing before evaluation or posting prevents the rebate.

## Read-only workflow

1. If the customer has not supplied a profile identifier, ask for their name, email address, or user ID. Do not expose unneeded profile data in the reply.
2. Use the supported user lookup, then `get_credit_card_accounts_by_user`. Select the account whose card type is exactly `Platinum Rewards Card`. If none exists, explain that the account cannot be found. If more than one matching account exists, ask the customer to identify the relevant account; do not combine accounts.
3. Obtain the current date with `get_current_time` and retrieve transaction history with `get_credit_card_transactions_by_user`.
4. Filter the history to the selected card. Treat a ledger date as `posted_date` only when the source establishes that it is the posting date and the transaction is final/posted. Classify each transaction as `eligible: true` only after screening it against the policy above. For example, an ordinary completed merchant purchase is normally eligible; a transaction whose type is unknown must not be assumed eligible.
5. Run `scripts/rebate_review.py` with the selected account's opening date, the current date, and the screened transactions. Supply the policy threshold and rebate amount. Set `account_active` and `product_unchanged` only when the account evidence supports those facts. Set `first_year_fee_waived` only when that status is established; do not infer a waiver merely from an opening date unless the applicable offer evidence explicitly permits that conclusion.
6. Use the result to answer plainly. State the evaluated cardmember-year dates, the $7,500-per-window rule, and whether every window met it. If it qualifies, say the expected rebate is $150 and clarify that it is posted as a statement credit after the annual fee is billed; do not claim it has already posted without billing/statement evidence.

## Interpreting incomplete or adverse results

- If `data_complete` is false, explain that the available data cannot support a definitive qualification decision. Do not convert unknown or non-posted transactions into qualifying purchases.
- If `spend_requirement_met` is false, name the deficient anniversary window(s), their eligible net-purchase total(s), and that a single missed window prevents the rebate for that cardmember year.
- If `qualification_status` is `conditional`, distinguish the verified spend result from the account-status or fee-waiver fact that remains unconfirmed.
- If no 12-month cardmember year has closed, explain when the first evaluation can occur rather than projecting qualification.
- Do not apply credits, alter the account, or promise a correction. This workflow is informational only.

## Script interface

Run `scripts/rebate_review.py` with one JSON object on stdin. Dates may be `YYYY-MM-DD` or `MM/DD/YYYY`; timestamps are accepted by their leading date.

Required fields:

- `account_open_date`: opening date of the selected account.
- `as_of_date`: current date/time.
- `transactions`: array of screened records. Each record needs `posted_date`, `amount`, and boolean `eligible`. Positive amounts add purchases; negative eligible amounts represent posted purchase returns/credits.

Recommended fields:

- `threshold`: use `7500.00`.
- `rebate_amount`: use `150.00`.
- `account_active`: `true`, `false`, or `null` if unknown.
- `product_unchanged`: `true`, `false`, or `null` if unknown.
- `first_year_fee_waived`: `true`, `false`, or `null` if unknown.

The script emits JSON only. Its `windows` array lists all 12 exact date ranges and their eligible totals. `spend_requirement_met` only reflects the monthly spend test. `qualification_status` incorporates known closure/product-change/waiver conditions but remains `conditional` if material account facts are unknown.

Example invocation pattern (with runtime-supplied data, not embedded customer values):

```text
run_skill_script(
  relative_path="scripts/rebate_review.py",
  input_json={"account_open_date": "<account opening date>", "as_of_date": "<current date>", "transactions": ["<screened transaction records>"], "threshold": "7500.00", "rebate_amount": "150.00", "account_active": true, "product_unchanged": true, "first_year_fee_waived": false}
)
```

Validate before replying that the output contains exactly 12 contiguous anniversary windows, each total is based only on screened posted net purchases, and the selected cycle ended before or on the as-of date.
