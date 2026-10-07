---
name: platinum-rewards-annual-fee-rebate-review
description: Review whether a Platinum Rewards Card cardmember-year meets the annual-fee rebate's monthly-spend requirement using posted transaction history. Use when a customer asks about the $7,500 monthly threshold, $150 rebate, qualifying windows, or anticipated rebate posting.
---

# Platinum Rewards annual-fee rebate review

Use this Skill to give a precise, account-specific eligibility explanation without making an unsupported statement that a credit has already posted.

## Product rules applied

* The monthly threshold is **$7,500.00** in net eligible posted purchases.
* The rebate is **$150.00**.
* A cardmember year contains 12 consecutive windows beginning on the account-opening monthly anniversary. A window ends the day before the next anniversary; treat the end date as inclusive when explaining it to the customer.
* Every one of the 12 windows must meet the threshold. One failed window disqualifies that cardmember year; there is no prorated rebate.
* Use posting dates, not authorization dates. Completed net purchases (including authorized-user, virtual-card, and international purchases) count. Fees, interest, adjustments, cash advances/equivalents, balance transfers, cash-like P2P/funding, and unresolved disputes do not. Refunds and credits reduce the window in which they post.
* A promotional first-year fee waiver means no rebate applies to that waived year. Under the documented promotion, a waiver was available only to accounts applied for and approved from 2024-06-01 through 2024-12-31. Do not infer a waiver merely from an account's age; check the applicable fee/promotion information.
* Evaluation occurs after the twelfth window closes. A qualified rebate is a statement credit after that cardmember year's annual fee is billed. It is not awarded if the account is closed or product-changed before evaluation or posting.

## Procedure

1. **Use existing context first.** If the conversation already supplies a verified customer identifier, account listing, current date, and transaction history, do not repeat those read-only lookups. Otherwise obtain the minimum identifier needed to locate the customer, then use `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user`.
2. Select the customer's **Platinum Rewards Card**, not a similarly named or other card product. If multiple Platinum Rewards accounts exist and transaction records cannot be attributed to the specific account, explain that the records are insufficient and obtain account-specific history rather than combining them.
3. Determine the completed cardmember year being asked about. For a current rebate inquiry, assess the most recent fully closed 12-window year. Do not treat a current, incomplete year as a completed qualification. If the customer asks about a specific billed year, use that year instead.
4. Confirm that the date supplied by the transaction source is its posted date (or use an explicit posting-date field). Do not substitute an authorization date. Normalize the relevant records into the JSON schema accepted by `scripts/review_rebate.py`, or supply the raw transaction-history result to that script.
5. Run the calculator. It uses decimal currency, filters evident excluded transactions, assigns each included amount to exactly one anniversary window, and reports all 12 totals and any failed windows.
6. Check the non-spend conditions separately: whether the evaluated year had an annual fee billed rather than a waiver, and whether the account remains open and unchanged through evaluation/posting. The normal account/transaction lookups may not establish those facts. Do not claim that a rebate has posted unless a source confirms it.
7. Respond plainly. State the evaluated year, the $7,500 per-window requirement, whether all 12 windows met it, and the $150 amount and timing if qualified. Mention a failed window's dates and total if not qualified. Keep detailed month-by-month totals available on request rather than exposing unnecessary transaction-level detail.

Suggested wording for a spend-qualified result:

> I reviewed the most recently completed cardmember year, [start] through [end]. Your eligible posted spending met the $7,500 monthly requirement in each of its 12 anniversary-date windows, so you meet the spending requirement for the $150 annual-fee rebate. The credit is applied after the annual fee for that year is billed, provided the year was fee-billed and the account remains open without a product change through evaluation and posting.

For a failure, say that the annual rebate is not earned for that entire cardmember year because at least one monthly window was below $7,500; do not suggest a partial credit.

## Calculator

Run `scripts/review_rebate.py` with JSON on standard input. It writes one JSON object to standard output.

Input fields:

```json
{
  "account_open_date": "YYYY-MM-DD",
  "as_of_date": "YYYY-MM-DD",
  "monthly_threshold": "7500.00",
  "rebate_amount": "150.00",
  "target_card_type": "Platinum Rewards Card",
  "transactions": [
    {
      "credit_card_type": "Platinum Rewards Card",
      "posting_date": "YYYY-MM-DD",
      "amount": "12.34",
      "status": "COMPLETED",
      "category": "Groceries",
      "transaction_kind": "purchase"
    }
  ],
  "fee_billed": true,
  "account_open_and_unchanged": true
}
```

`evaluation_start` may be supplied as a `YYYY-MM-DD` monthly anniversary to review a particular completed cardmember year. Otherwise the script finds the most recently completed year as of `as_of_date`. `fee_billed` and `account_open_and_unchanged` are optional; omit either when the source does not establish it. Negative purchase/refund amounts are deliberately included as reductions.

As an alternative to `transactions`, provide `transactions_text` containing the result text from `get_credit_card_transactions_by_user`. The parser recognizes the standard transaction-history fields (`credit_card_type`, `transaction_amount`, `transaction_date`, `category`, and `status`) and treats `transaction_date` as the supplied posting date. Only use that alternative when the history date is the posted date in the supplied data.

The output contains `monthly_windows`, `failed_windows`, `spend_requirement_met`, and a conservative `decision`:

* `eligible` means the spend test passed and both supplied non-spend conditions were true.
* `not_eligible_spend` means one or more windows failed.
* `not_applicable_fee_waived` means the supplied evaluated year was not fee-billed.
* `spend_qualified_pending_account_conditions` means all windows passed but fee billing and/or open, unchanged account status was not established.

The script rejects an incomplete requested year, missing/invalid records, and anniversary days after the 28th because the supplied policy does not define how an absent calendar anniversary should be handled. In those cases, obtain the missing information or applicable product policy instead of inventing a result.

## Validation before responding

Verify that the report has exactly 12 contiguous windows, each shows a decimal total, and every included record is on or after the year start and before the next annual anniversary. Ensure the response distinguishes (1) meeting the spend test, (2) fee-billed-year applicability, and (3) actual rebate posting. This inquiry is read-only; do not attempt to create a statement credit or alter the account.
