---
name: platinum-rewards-annual-fee-rebate-review
description: Review a Platinum Rewards Card customer's annual-fee rebate eligibility from account opening, posting-date transactions, and an as-of date. Use for a request to explain or check the $150 rebate that requires $7,500 in qualifying spend in every monthly anniversary window.
---

# Platinum Rewards annual-fee rebate review

Use this Skill to provide an accurate, privacy-conscious eligibility review. It evaluates the most recently completed fee-billed cardmember year; it does not issue a credit or make any account change.

## Policy applied

- The rebate is $150 and the monthly threshold is $7,500 of net qualifying spend.
- Every one of the 12 monthly windows must meet the threshold. One short window disqualifies the whole year; there is no prorated rebate.
- A window begins on the monthly anniversary of the cardmember-year start and ends the day before the next anniversary. Use the **posting date**, not authorization or statement date.
- Completed posted purchases, including authorized-user, virtual-card, and international purchases, count. Credits/refunds/returns reduce the window in which they post.
- Fees, interest, adjustments, balance transfers, cash advances, and cash-equivalent/person-to-person funding activity do not count. Unresolved disputed activity does not count.
- A confirmed first-year promotional fee waiver means no rebate applies to that waived first year. The first potentially eligible year begins at its first anniversary. Do not infer promo eligibility merely from the opening date: the offer also required an application during and approval in its stated promo period.
- A qualified customer receives the credit after the applicable annual fee is billed. A closed or product-changed account before evaluation or posting cannot receive it.

## Safe account-review workflow

1. Locate the customer using an offered identifier. Select only the Platinum Rewards Card, and confirm the account-opening date and whether the account remains open and has not product-changed.
2. Before disclosing transaction totals or account-specific eligibility to an unverified caller, obtain and confirm at least two of date of birth, email, phone number, and address against the customer record. Log verification with the normal `log_verification` tool and the current time. A name or user ID locates a record but is not itself two-field verification.
3. Retrieve the card accounts and transaction history with the normal banking tools. Do not request a card number. If more than one matching Platinum account exists and transactions cannot be attributed to one account, explain that a definitive review is unavailable rather than combining accounts.
4. Determine the latest 12-window cardmember year whose last window has closed as of the current date. If the first year is a **confirmed** fee-waived promo year, exclude it and assess the latest fully completed subsequent year. Do not assess an in-progress year as final eligibility.
5. Normalize the selected account's transactions into the JSON schema below and run `scripts/rebate_evaluator.py`. Supply only transactions whose card attribution is known. Use a true posted date where available. If the history is known to be partial, set `history_complete` to `false`.
6. Interpret results:
   - `eligible`: every closed window reached $7,500 and the account is active/not product-changed. State that the customer qualified based on the reviewed history and that the $150 statement credit is applied after the applicable annual fee is billed; do not claim it has already posted unless a separate account record confirms that.
   - `not_eligible`: state the first (and optionally all) windows below threshold, their net qualifying total, and the shortfall. Explain one short month disqualifies that cardmember year.
   - `insufficient_information`: do not guess. State whether the year is incomplete, transaction history is incomplete, dates cannot be evaluated, or account status/promo facts are missing.
7. Keep the customer-facing reply concise: result, evaluation period, relevant shortfall(s) if any, and the posting-date/monthly-anniversary rule. Do not expose unnecessary transaction-level details or unrelated account information.

## Evaluator interface

Run:

```text
python3 scripts/rebate_evaluator.py < review.json
```

The script receives one JSON object on stdin and emits one JSON object on stdout.

Required fields:

```json
{
  "account_open_date": "YYYY-MM-DD",
  "as_of_date": "YYYY-MM-DD",
  "transactions": []
}
```

Optional review controls:

- `threshold`: decimal or money string; defaults to `7500.00`.
- `first_year_fee_waived`: boolean. Set true only when waiver applicability is confirmed.
- `account_active`: boolean; defaults to true. Set false for an account closed or product-changed before evaluation/posting.
- `history_complete`: boolean; defaults to true. Set false if the retrieved record may omit transactions.
- `transactions_card_attributable`: boolean; defaults to true. Set false if the source cannot identify which matching card generated the transactions.
- `cardmember_year_start`: optional `YYYY-MM-DD` override when a reliably documented fee-billed year begins on a date other than the normal applicable anniversary.

Each transaction must contain `posted_date` (or `transaction_date`) and `amount`. `amount` may be a number or a currency-formatted string. Negative qualifying amounts reduce a window. For reliable classification, also provide `is_eligible: true` or `false`; this explicit field takes precedence. Without it, the evaluator counts only `COMPLETED`/`POSTED` transactions and excludes recognized statuses/categories/types such as fees, interest, adjustments, balance transfers, cash advances, cash equivalents, P2P transfers, funding transactions, and unresolved disputes. Unknown classifications are returned as warnings and make the outcome insufficient rather than silently counting them.

The evaluator deliberately refuses anniversary starts after the 28th because the supplied policy does not say how to handle a missing calendar day (for example, a 31st in February). Obtain the governing rule or perform a documented manual review instead of inventing a convention.

## Output validation

Before relying on the output, check that:

- `status` is not `insufficient_information`;
- `evaluation_start` and `evaluation_end_exclusive` cover exactly 12 windows;
- `windows` contains 12 nonoverlapping start/end ranges;
- every stated total is derived only from transactions inside that range and classified eligible; and
- an `eligible` result has every `meets_threshold` value true and `account_active` true.

The output uses money strings with two decimal places, so it can be quoted directly without floating-point rounding.
