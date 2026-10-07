---
name: platinum-rewards-annual-fee-rebate-review
description: Review whether a Platinum Rewards Card cardmember year meets the annual-fee rebate spend requirement. Use for authenticated customers asking about the $150 rebate, anniversary-window spend, or why a rebate was not received.
---

# Platinum Rewards annual-fee rebate review

Use this Skill to perform a read-only eligibility review. It determines the spend result; it does **not** post, request, promise, or manually apply a rebate.

## Policy applied

- The rebate amount is **$150.00** and the monthly threshold is **$7,500.00**.
- A cardmember year comprises 12 consecutive account-anniversary windows. Each window starts on the account-opening calendar day and ends the day before the next anniversary.
- Every one of the 12 windows must meet the threshold. There is no partial or prorated rebate.
- Count only net posted purchases, including authorized-user, virtual-card, and international purchases. Exclude fees, interest, adjustments, cash advances/cash equivalents, balance transfers, P2P/cash-equivalent funding, and unresolved disputes. Returns/refunds/credits reduce the window in which they post.
- A fee-waived first cardmember year is not rebate eligible. The documented first-year-fee waiver applied only to accounts opened from 2024-06-01 through 2024-12-31; a fee-billed year begins after a waived first year.
- Evaluation is after the 12th window closes. The account must not have been closed or product-changed before evaluation or posting, and the annual fee for that year must be billed before the rebate is posted.

## Required secure workflow

1. **Verify identity before disclosing account-specific transaction totals, eligibility, or account details.** A name lookup locates a possible record but is not verification. Ask the customer to confirm any two of the four on-file fields: date of birth, email, phone number, and address. Do not reveal a field in the prompt.
2. Compare the two supplied values to the located record. If both match, get the current timestamp and call `log_verification` with all required on-file fields and the timestamp. If they do not match, do not disclose the review; request another verification field or use the applicable support process.
3. Obtain the customer’s card accounts and select the **Platinum Rewards Card**. If there are multiple matching Platinum cards and transactions cannot be associated with one account, explain that the available data cannot support an account-specific result.
4. Obtain the card transaction history. Use the recorded posting date. If the available history exposes only a completed transaction date, describe the conclusion as based on the available completed transaction records; do not treat an authorization date as posted spending.
5. Determine the most recent **completed fee-billed** cardmember year. Do not evaluate an in-progress year as final. A customer whose opening date falls in the documented promo interval has a waived first year; otherwise do not invent a waiver. If fee-billing history or lifecycle status is unavailable, give the spend result and clearly state the remaining condition rather than claim that a credit has posted.
6. Normalize the selected card’s transactions and run `scripts/review_rebate.py`. Present the reviewed anniversary dates, all 12 monthly totals, the threshold, and any month below threshold. Keep the explanation concise and do not expose unrelated account data.

## Running the calculator

The script reads one JSON object from stdin and writes one JSON object to stdout. It uses only the standard library.

Example invocation pattern:

```text
python scripts/review_rebate.py < review_input.json
```

Input fields:

- `account_open_date` and `as_of_date`: required ISO dates (`YYYY-MM-DD`).
- `transactions`: selected Platinum-card transactions only. Each item should contain `posting_date`, `amount`, `status`, and either `transaction_kind` or `counts_toward_threshold`.
  - Use `transaction_kind` values such as `purchase`, `virtual_purchase`, `international_purchase`, `return`, `refund`, `credit`, `fee`, `interest`, `cash_advance`, `cash_equivalent`, `balance_transfer`, or `p2p_transfer`.
  - `counts_toward_threshold: true` or `false` overrides kind classification when the transaction system provides a definitive determination.
  - Use a negative amount for a posted return/refund/credit if the system does not already do so.
  - Only map `COMPLETED` to a posted status when the transaction source treats that value as a posted record. The optional `posted_statuses` field defaults to `["POSTED", "COMPLETED"]`.
- Optional `fee_billed_year_start`: an ISO date for the actual fee-billed cardmember year being reviewed. It must be an account anniversary. If omitted, the script selects the latest completed annual cycle, skipping the documented waived first year when applicable.
- Optional `first_year_fee_waived`: explicit boolean. If omitted, the documented 2024-06-01 through 2024-12-31 promo interval is used.
- Optional `annual_fee_billed` and `account_active_and_unchanged`: booleans. Supply them only when supported by account/billing records. If unknown, the script reports a spend result pending those conditions.
- Optional `anniversary_day_resolution`: `strict` (default) or `clamp`. The policy does not define a non-existent anniversary day for accounts opened on the 29th–31st; leave `strict` unless a governing rule authorizes clamping.

Meaningful output checks:

- `window_count` must be 12 and `annual_year_end` must be before `as_of_date` for a final annual review.
- Each `windows[]` entry has inclusive `start`/`end`, `net_qualifying_spend`, `meets_threshold`, and any unclassified transaction IDs.
- `spend_requirement` is `met`, `missed`, or `indeterminate`. A below-threshold month with unclassified in-window activity is indeterminate rather than a confirmed miss.
- `qualification_status: eligible` requires a met spend requirement plus explicit `annual_fee_billed: true` and `account_active_and_unchanged: true`. A pending status is not a promise that the rebate will post.

## Customer response guidance

For a confirmed qualifying review, say that the customer met the $7,500 requirement in each of the 12 stated anniversary windows and is eligible for the $150 rebate subject to the annual fee having been billed and the account remaining eligible; it is applied as a statement credit after billing. For a miss, identify the relevant window(s), total(s), and that one missed month disqualifies the whole year. For an in-progress, ambiguous, or incomplete-data case, say exactly what cannot yet be confirmed. Do not transfer or perform an account-changing action merely to calculate the review.
