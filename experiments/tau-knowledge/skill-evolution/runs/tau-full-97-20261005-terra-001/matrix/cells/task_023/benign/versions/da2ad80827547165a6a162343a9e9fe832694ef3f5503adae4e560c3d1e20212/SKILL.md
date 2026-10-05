---
name: platinum-rewards-annual-fee-rebate-review
description: Review an authenticated customer's Platinum Rewards Card annual-fee rebate spend requirement using account-anniversary windows, and arrange a consented human handoff for an unsupported premium-card application or upgrade request.
---

# Platinum Rewards annual-fee rebate review

Use this Skill for an authenticated customer asking whether a Platinum Rewards Card qualifies for its annual-fee rebate, why it did not qualify, or for a related request to speak with a specialist about a premium-card application or upgrade. This is a read-only eligibility review: do **not** post, request, promise, or manually apply a rebate.

## Policy applied

- The rebate amount is **$150.00** and the monthly threshold is **$7,500.00**.
- A cardmember year comprises 12 consecutive account-anniversary windows. Each window starts on the account-opening calendar day and ends the day before the next anniversary.
- Every one of the 12 windows must meet the threshold. One missed month disqualifies the entire year; there is no partial or prorated rebate.
- Count only net posted purchases, including authorized-user, virtual-card, and international purchases. Exclude fees, interest, adjustments, cash advances/cash equivalents, balance transfers, P2P/cash-equivalent funding, and unresolved disputes. Returns, refunds, and credits reduce the window in which they post.
- A fee-waived first cardmember year is not rebate eligible. The documented first-year-fee waiver applies only to accounts opened from 2024-06-01 through 2024-12-31. A fee-billed year begins after a waived first year.
- Evaluation occurs after the 12th window closes. The annual fee must be billed before a qualified rebate can be applied as a statement credit, and an account closed or product-changed before evaluation or posting is not eligible.

## Required secure workflow

1. **Verify identity before disclosing account-specific transaction totals, eligibility, or account details.** A name lookup only locates a possible record; it is not verification. Ask the customer to provide any two of these on-file fields: date of birth, email, phone number, and address. Do not reveal a value in the prompt.
2. Compare the two supplied values to the located record. If both match, obtain the current timestamp and call `log_verification` with the required on-file fields and timestamp. If they do not match, do not disclose the review; request another field or follow the applicable support process.
3. Obtain the customer's card accounts and select the **Platinum Rewards Card**. If multiple matching Platinum accounts cannot be distinguished by the available transaction data, explain that an account-specific result cannot be supported.
4. Obtain transaction history for the selected card. Use the recorded posting date. If the source exposes only a completed transaction date, state that the calculation is based on the available completed transaction records; do not represent it as an authorization date.
5. Normalize source values before calculation. Convert supported source date formats, including `MM/DD/YYYY` when supplied by the transaction system, to ISO `YYYY-MM-DD` for the script. Preserve source amounts and map transaction classifications only where the source provides enough information. Do not silently classify an unknown transaction as qualifying.
6. Determine the most recent **completed fee-billed** cardmember year. Do not treat an in-progress year as final. Apply the documented waiver only where its opening-date condition is met; do not invent a waiver. If fee-billing history or lifecycle status is unavailable, report the spend result but state the remaining unconfirmed condition.
7. Run `scripts/review_rebate.py` using selected-card transactions. Give the reviewed annual dates, 12 monthly totals, threshold, and any below-threshold window. Do not expose unrelated account data.

## Running the calculator

The script reads one JSON object from stdin and writes one JSON object to stdout. It uses only the Python standard library.

```text
python scripts/review_rebate.py < review_input.json
```

Input schema:

- `account_open_date` and `as_of_date`: required ISO dates (`YYYY-MM-DD`).
- `transactions`: selected Platinum-card transactions only. Each item contains `posting_date`, `amount`, `status`, and either `transaction_kind` or `counts_toward_threshold`.
  - `transaction_kind` may be `purchase`, `virtual_purchase`, `international_purchase`, `return`, `refund`, `credit`, `fee`, `interest`, `cash_advance`, `cash_equivalent`, `balance_transfer`, or `p2p_transfer`.
  - `counts_toward_threshold: true` or `false` overrides kind classification where the transaction source makes that determination.
  - Use a negative amount for a posted return/refund/credit when the source does not already use one.
  - Map `COMPLETED` to a posted status only if the source defines it as a completed/posted record. `posted_statuses` defaults to `["POSTED", "COMPLETED"]`.
- Optional `fee_billed_year_start`: an ISO account-anniversary date for the actual fee-billed year. If omitted, the script selects the latest closed annual cycle and skips the documented waived first year where applicable.
- Optional `first_year_fee_waived`: explicit boolean, only when supported by billing or offer records. If omitted, the documented promo interval is applied.
- Optional `annual_fee_billed` and `account_active_and_unchanged`: booleans only when supported by records. Omit unknown values.
- Optional `anniversary_day_resolution`: `strict` (default) or `clamp`. The policy does not define a non-existent anniversary day for accounts opened on the 29th–31st, so retain `strict` unless an authorized rule supplies `clamp`.

Output validation:

- Confirm `window_count` is 12 and `annual_year_end` is before `as_of_date` for a final annual review.
- Each `windows[]` item has inclusive `start` and `end`, `net_qualifying_spend`, `meets_threshold`, and unclassified transaction IDs.
- `spend_requirement` is `met`, `missed`, or `indeterminate`. A below-threshold window containing unclassified activity is indeterminate, not a confirmed miss.
- `qualification_status: eligible` requires `spend_requirement: met` plus explicit `annual_fee_billed: true` and `account_active_and_unchanged: true`. A pending status is never a promise that the rebate will post.

## Customer response guidance

For a completed annual review with all windows above threshold, explicitly say: **“Your spend requirement is met.”** State the completed cardmember-year date range, that all 12 anniversary windows met the $7,500 threshold, and that the review is based on the available completed transaction records when applicable. State that the rebate amount is $150.00.

When annual-fee billing or continuing account status is not observed, clearly distinguish the spend conclusion from final rebate posting: explain that the spend requirement is met, but that you **cannot confirm** the annual fee was billed, the account remains eligible, or that a statement credit has posted. A qualifying rebate is applied as a statement credit after the annual fee is billed.

For a miss, identify the relevant window(s) and totals and explain that one month below $7,500 disqualifies the entire year. For an in-progress, ambiguous, or incomplete-data case, say exactly what cannot yet be confirmed. Do not transfer or perform an account-changing action merely to calculate a rebate review.

## Premium-card application or upgrade handoff

A request to apply for or upgrade to a premium product that is not supported by the available self-service workflow requires a specialist handoff.

1. Explain briefly that a human specialist can review the request.
2. Obtain explicit customer consent before transferring them. A request for a specialist or human agent counts as consent only when it is clear and current; if uncertain, ask for confirmation.
3. After consent, call `transfer_to_human_agents` with `reason: "specialized_department_required"`. Put the material context in `summary`: the premium product or tier requested, any invitation mentioned by the customer, and whether they seek an application or upgrade review. Do not add unsupported eligibility, product, or account facts.
4. Confirm the handoff only after the transfer tool reports success. Tell the customer they have been transferred or connected to a human agent. If the transfer fails, state that it did not complete and use the applicable recovery process; do not claim success.
