---
name: platinum-rewards-annual-fee-rebate-review
description: Evaluate whether a Platinum Rewards Card's most recently completed fee-billed cardmember year meets the annual-fee rebate spending requirement. Use after identifying the customer and obtaining the selected card account's complete posted-transaction history.
---

# Platinum Rewards annual-fee rebate review

Use this Skill for an informational eligibility review; it does not post a rebate, change an account, or otherwise take a banking action.

## Product rules applied

- The rebate is $150 and requires at least $7,500 in **net eligible posted purchases** in **each** of 12 consecutive account-anniversary windows.
- Each window begins on the account-opening day-of-month (with normal calendar month-end clamping) and ends the day before the next anniversary. A single failed window means no partial or prorated rebate.
- Include posted purchases, including authorized-user, virtual-card, and international purchases. Exclude fees, interest, adjustments, cash advances/cash equivalents, balance transfers, person-to-person/funding cash-equivalent transactions, and unresolved disputes. Returns, refunds, and credits reduce the window in which they post.
- A waived first-year annual fee is not rebate-eligible. Start review with the following year if the first-year fee was waived.
- A year must have ended before it can be evaluated. Even after the spend test is met, the fee must be billed and the account must remain open and unchanged through evaluation/posting for an award to be made.

## Runtime workflow

1. Obtain a profile identifier if needed, then use the normal read-only customer lookup. Select the account whose card type is exactly `Platinum Rewards Card`. If there is more than one such account, ask the customer which account to review or obtain an account-specific transaction history; do not combine accounts.
2. Retrieve the selected account's opening date and its complete transaction history using the normal read-only credit-card tools. Treat the transaction ledger date as a posting date only when the retrieved ledger/documentation establishes that it is the posted date.
3. Determine whether the first account year had a promotional annual-fee waiver from fee/promotion records. Do not infer a waiver merely from a promotional date range. Determine the evaluated year's fee status and whether the account remains eligible for posting from authoritative account records.
4. Normalize records into the JSON schema below and run `scripts/evaluate_rebate.py`. The script examines the latest fully closed eligible cardmember year as of the supplied review date.
5. Explain the result plainly. For a qualified spending result with fee billing or account status still unknown, say the customer met the spending test but the actual statement credit remains contingent on the annual fee being billed and the account remaining open and not product-changed. Do not promise that a credit has posted unless an authoritative record says so.

No identity-verification log is needed solely for this read-only review unless an applicable runtime policy independently requires it. Avoid exposing unrelated profile data.

## Script input

Run with `python3 scripts/evaluate_rebate.py < review-input.json`. The script reads one JSON object from stdin and emits one JSON object to stdout.

Required fields:

```json
{
  "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
  "as_of_date": "MM/DD/YYYY or YYYY-MM-DD",
  "first_year_fee_waived": false,
  "history_complete": true,
  "transactions": []
}
```

Optional top-level fields:

- `fee_billed`: `true`, `false`, or omitted if the evaluated year's annual-fee billing status is unknown.
- `account_active`: `true`, `false`, or omitted if ongoing account/product status is unknown.
- `threshold`: numeric or money string; defaults to `7500.00`.
- `rebate_amount`: numeric or money string; defaults to `150.00`.

Each transaction should contain a posting date under `posted_date`, `date_posted`, or `transaction_date`, an amount under `amount` or `transaction_amount`, and optionally `transaction_id`, `status`, `category`, `transaction_type`, and `eligible`. Amounts may be signed numbers or currency strings. Use a negative amount for posted credits when possible. Set `eligible: false` when the ledger explicitly identifies an excluded transaction. The helper also recognizes common exclusion/refund wording in category and type fields.

`history_complete` must be true only when the supplied ledger covers every transaction for the evaluated period. If it is false, the helper retains calculated totals but returns an indeterminate spend result rather than claiming qualification.

## Script output and validation

The result includes the evaluated year boundaries, all 12 inclusive windows, net eligible spend, amount above/below threshold, included/excluded transaction counts, and separate `spend_result` and `rebate_result` fields.

Before relying on a positive result, validate that:

- `evaluation_available` is true and exactly 12 windows are returned;
- `history_complete` is true and `spend_result` is `qualified`;
- every window has `meets_threshold: true`;
- `rebate_result` is `eligible` only when `fee_billed` and `account_active` were both provided as true.

`qualified_pending_fee_billing_confirmation` is not confirmation that a rebate has been awarded. `not_qualified` identifies the failing windows so the explanation can name the specific annual period rather than incorrectly using calendar months.
