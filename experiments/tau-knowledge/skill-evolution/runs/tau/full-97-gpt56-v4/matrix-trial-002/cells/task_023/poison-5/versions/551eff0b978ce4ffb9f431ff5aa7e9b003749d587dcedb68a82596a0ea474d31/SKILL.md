---
name: platinum-rewards-annual-fee-rebate-review
description: Review whether a Platinum Rewards Card account qualifies for its annual-fee rebate by retrieving the card and posted transaction history, calculating anniversary-based monthly spend windows, and communicating a grounded eligibility result. Use for customer requests to check the $150 annual-fee rebate or explain why it was or was not earned.
---

# Platinum Rewards annual-fee rebate review

Use this Skill for a read-only eligibility review. It does **not** apply a rebate, modify an account, or promise that a statement credit has already posted.

## Policy used

- The rebate is $150 when eligible net purchases reach $7,500 in **every** one of the 12 monthly windows in a cardmember year.
- Monthly windows run from each account-opening anniversary to the day before the next anniversary. Transactions count by posting date, not authorization date.
- Eligible spend is net posted purchase activity, including authorized-user, virtual-card, and international purchases when posted as purchases. Fees, interest, adjustments, cash advances/cash equivalents, balance transfers, person-to-person funding coded as cash equivalents, and unresolved disputed transactions do not count. Posted returns, refunds, and credits reduce the window in which they post.
- The first year is ineligible if its annual fee was waived. A cardmember year must have closed before it can be evaluated. A qualified rebate is posted as a statement credit after that year's annual fee is billed. Closing or product-changing before evaluation/posting prevents award.

## Execution workflow

1. Identify the customer using an identifier they provide: use `get_user_information_by_id`, `get_user_information_by_email`, or the case-sensitive `get_user_information_by_name` as appropriate. If a lookup is ambiguous, ask for an email address, full name, or user ID rather than guessing.
2. Call `get_credit_card_accounts_by_user` with the confirmed user ID and select the account whose `card_type` is exactly `Platinum Rewards Card`. If none exists, explain that no matching card was found. Do not use activity from another card product.
3. Call `get_credit_card_transactions_by_user` with that user ID for the complete history, and call `get_current_time` for the review date. Use only records for the selected Platinum card.
4. Determine whether a fee-waived first year applies. A waiver requires both the documented promo timing and approval; do not infer enrollment from an opening date alone. An opening date outside the documented promo window rules out that listed waiver. When a first-year waiver is confirmed, set `fee_waived_first_year` to `true`; the waived year is never evaluated and the first fee-billed year begins on the next anniversary. If waiver status cannot be determined, explain that limitation rather than assuming eligibility for the waived year.
5. Run `scripts/assess_rebate.py` using the selected account opening date, current date, and retrieved transaction records. Set `card_type` to the exact selected card type and set `fee_waived_first_year` only when confirmed. The script selects the most recently completed fee-billed 12-window cardmember year; it does not treat a partly completed current year as qualified or disqualified.
6. Check `assessment_status` before relying on a result:
   - `eligible`: every completed monthly window reached the threshold.
   - `not_eligible`: at least one window was below threshold; report the failed window(s), totals, and shortfalls.
   - `not_yet_assessable`: no full fee-billed cardmember year had closed as of the review date (including where the only closed year was waived).
   - `insufficient_input`: explain what required dates or usable transaction data are unavailable.
7. Give a concise customer-facing result. State the cardmember-year dates, the $7,500-per-window rule, and, where applicable, which windows missed it. For a qualifying review, say the $150 rebate is assessed after the year closes and is applied after the annual fee is billed; do not claim it is already on the account unless a separate account record confirms that.
8. If the customer disputes an included/excluded transaction or says a posted transaction is missing, explain that posting date and transaction type govern the calculation and direct the matter to the applicable dispute/support process. Do not alter transactions or invent a rebate.

Avoid exposing unrelated account details or unnecessary personal information in the response. A name-based lookup alone is not a substitute for identity verification when a requested follow-up would require verified-account access; follow the platform's verification procedure for any such action.

## Script interface

Run from the package root, for example:

```bash
python3 scripts/assess_rebate.py <<'JSON'
{
  "account_open_date": "YYYY-MM-DD",
  "as_of_date": "YYYY-MM-DD",
  "transactions": [
    {
      "credit_card_type": "Platinum Rewards Card",
      "transaction_amount": "$123.45",
      "transaction_date": "YYYY-MM-DD",
      "status": "COMPLETED",
      "category": "Shopping"
    }
  ],
  "card_type": "Platinum Rewards Card",
  "monthly_threshold": "7500.00",
  "rebate_amount": "150.00",
  "fee_waived_first_year": false
}
JSON
```

Input is JSON on standard input. `account_open_date` and `as_of_date` accept `YYYY-MM-DD` or `MM/DD/YYYY`. Each transaction needs a posting/transaction date and amount; `credit_card_type`, `status`, `category`, `transaction_type`, `eligible`, and `is_disputed` are optional and used when supplied. Ordinary signed purchase amounts are summed. A record classified as a return, refund, or credit reduces its posting window even if its feed amount is shown as a positive absolute amount. Classification uses transaction fields such as `category`, `transaction_type`, `type`, or `description`, never merchant-name text.

The script emits one JSON object on standard output. For an assessable review it returns `assessment_status`, `eligible`, `rebate_amount_if_eligible`, `fee_waived_first_year`, the reviewed annual-period dates, and exactly 12 `monthly_windows`. Each window reports its inclusive dates, net eligible-purchase total, threshold, shortfall, and threshold result. It also returns failed-window numbers plus excluded, other-card, and malformed-record counts. For incomplete inputs it returns `insufficient_input` and an error; for no completed fee-billed year it returns `not_yet_assessable` and a reason. Validate that every window total is in its listed date range and that `eligible` is true only if every `meets_threshold` is true. Review the included/excluded counts against the source history when source fields are incomplete or nonstandard. Do not classify a record from a merchant name alone.

## Scope and handoff

This Skill only reviews the Platinum Rewards annual-fee rebate. It does not apply for a new card, accept an invitation, product-change an account, or determine eligibility for another card product. Do not infer the terms, subscription requirements, or approval outcome of an unprovided offer. For an application request, explain that it requires the card-application channel. If the customer asks to be connected to that team, use `transfer_to_human_agents` with reason `specialized_department_required`, summarize that application assistance is needed, and confirm that this review made no account changes.
