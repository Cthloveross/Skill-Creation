---
name: platinum-rewards-annual-fee-rebate-review
description: Review a Platinum Rewards Card annual-fee rebate request by selecting the most recently completed fee-billed cardmember year, totaling eligible posted net purchases in anniversary-date monthly windows, and explaining qualification or a limitation without issuing a credit. Use for account-specific rebate eligibility questions.
---

# Platinum Rewards annual-fee rebate review

Use this Skill when a customer asks whether their Platinum Rewards Card qualified for the annual-fee rebate. The rebate is **$150** when eligible posted net purchases reach **$7,500 in every one of 12 monthly anniversary windows** in a fee-billed cardmember year. A single failing window disqualifies the entire year.

## Required account review

1. Identify the customer and retrieve their credit-card accounts. Select only the `Platinum Rewards Card` account the customer is asking about. If multiple indistinguishable Platinum accounts exist and the transaction feed cannot associate transactions with an account ID, ask the customer which account to review rather than combining activity.
2. Retrieve the current time and the customer's complete credit-card transaction history. Filter to the selected card product; do not include another card product's transactions.
3. Establish the applicable fee-billed cardmember year:
   - Monthly windows begin on the account-opening calendar-day anniversary and end the day before the next anniversary.
   - The first year is excluded only when a first-year fee waiver actually applied. The documented waiver applied only to accounts approved during 2024-06-01 through 2024-12-31; do not infer approval merely from an opening date unless account evidence establishes it.
   - Usually review the most recently completed 12-window fee-billed year. Do not claim eligibility for a still-open year.
4. Normalize the account and transaction data and run `scripts/evaluate_rebate.py`. It performs the repeatable window and amount calculation.
5. Explain the result plainly. Cite the qualifying/failing windows and their net eligible totals as appropriate. State that the calculation uses posting dates, not authorization dates.

## Eligible-amount rules

Count completed/posted purchase activity, including authorized-user, virtual-card, and international purchases when they post as purchases. A completed return, refund, or credit must reduce the total in the window in which it posts.

Exclude fees, interest, adjustments, cash advances, cash-equivalent activity, balance transfers, and person-to-person/funding transfers coded as cash equivalents. Exclude pending or unresolved disputed activity. If the feed does not identify transaction type/category/status sufficiently to apply a rule, describe the limitation; do not silently count it.

## Running the calculator

The script reads one JSON object from standard input and emits one JSON object on standard output. It uses only the supplied runtime data and does not make banking calls or issue any rebate.

Example invocation pattern (substitute real account data; do not copy example values into a customer review):

```json
{
  "account_open_date": "YYYY-MM-DD",
  "as_of_date": "YYYY-MM-DD",
  "transactions": [
    {
      "credit_card_type": "Platinum Rewards Card",
      "transaction_date": "YYYY-MM-DD",
      "transaction_amount": "$0.00",
      "status": "COMPLETED",
      "category": "Shopping"
    }
  ],
  "annual_fee_waived_first_year": false,
  "account_open": true,
  "product_changed": false
}
```

Inputs:

- `account_open_date` and `as_of_date` are required. Dates may be `YYYY-MM-DD` or `MM/DD/YYYY`.
- `transactions` is the complete history available for the selected product. `transaction_amount` may be signed and may contain `$` and commas.
- `annual_fee_waived_first_year` should be supplied only when supported by account/promotion evidence. It defaults to `false`.
- To review a particular completed fee-billed year, provide `evaluation_year_start` (an anniversary date). Otherwise, the script chooses the latest completed fee-billed year.
- Set `account_open` or `product_changed` to `false` when account evidence shows closure or a product change before evaluation/posting. In that case a rebate cannot be awarded.
- Optional `threshold` and `rebate_amount` support products with different disclosed terms but default to `7500.00` and `150.00`.

Output contains `result` (`qualified`, `not_qualified`, `not_yet_complete`, `unavailable`, or `not_awardable`), the evaluated dates, each window total, failing windows, excluded-record reasons, and any warnings. Currency values are decimal strings.

## Validation before responding

Check that exactly 12 contiguous windows were evaluated, each ends the day before the next anniversary, and only records dated within `[window_start, next_window_start)` were included. Confirm the selected evaluation year had closed as of the supplied current date. A qualified calculation establishes eligibility only; transaction history alone does not establish whether an annual fee was billed or whether the statement credit has already posted.

If the result is `not_awardable`, explain that closure or product change before evaluation/posting prevents the rebate. If it is `unavailable` or the history is incomplete/ambiguous, explain what evidence is missing and avoid a definitive determination. Do not use this Skill to post, adjust, or promise a credit; use only declared banking tools and documented procedures if a separate action is available.
