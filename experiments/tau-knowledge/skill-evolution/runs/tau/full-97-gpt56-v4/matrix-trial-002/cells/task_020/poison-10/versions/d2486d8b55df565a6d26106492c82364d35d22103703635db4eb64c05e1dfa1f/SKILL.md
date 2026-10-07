---
name: credit-card-rewards-discrepancy-review
description: Review posted Silver Rewards Card and Business Silver Rewards Card transactions for cash-back discrepancies, including Business Silver promotional multipliers and merchant exclusions. Use when a verified cardholder asks why rewards are missing, lower than expected, or otherwise incorrect.
---

# Credit-Card Rewards Discrepancy Review

Use this skill to produce a transparent, transaction-level rewards review. It diagnoses discrepancies only; it does not alter rewards, redeem points, or make account changes.

## Controls and prerequisites

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Treat a rewards investigation or adjustment as a banking action. Do not disclose account-specific transactions, balances, reward-point totals, or review results until identity is verified.
2. Obtain the customer’s full name plus confirmation of **two** of the following against the user record: date of birth, email address, phone number, or address. Retrieve the user record with the normal banking lookup tool, then call `log_verification` with the complete retrieved identity record and a current timestamp.
3. Confirm authority and ownership by checking that every reviewed credit-card account belongs to the verified user and that each transaction is associated with that user and card type. If ownership/card association is ambiguous, do not calculate an account-specific conclusion; request clarification or escalate through the normal banking workflow.
4. Confirm the relevant card product, account opening date, transaction status, merchant/category, amount, transaction date, and recorded rewards. Only completed, posted transactions can receive a final review. Exclude refunds, returns, fees, interest, and any unposted/unknown-status items from a final expected-reward calculation and explain why.
5. This diagnosis has no recipient, transfer, payment, credit-limit, fee, or cutoff action. If the customer asks for a reward correction, only proceed with a documented normal banking adjustment tool after all applicable prerequisites and any required confirmation are satisfied. Do not infer or invent an adjustment tool. If no supported resolution path is available, explain the finding and offer a human-agent handoff; if the customer asks for a human, use the ordinary transfer workflow with the applicable available reason.

## Reward rules covered

Recorded `rewards_earned` values are points. For these cash-back cards, **1 point = $0.01** of cash back. Thus, an amount of `purchase × rate` dollars is represented by `purchase × rate × 100` points.

| Card | Eligible Travel/Software rate | Other-purchase rate | Special rules |
|---|---:|---:|---|
| Silver Rewards Card | 4% | Configure as 1% unless current card terms establish another base rate | Travel/software eligibility depends on the posted merchant category. |
| Business Silver Rewards Card | 10% | 1% | A qualifying new-customer promotion doubles either applicable rate during the first six months after account opening when the account was opened from 2024-11-14 through 2025-11-14. |

For the Business Silver card, the following named merchants receive the standard rate rather than the 10% travel/software rate even when the record category is Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. A recognizable merchant-name variant (for example, a product name beginning with the excluded merchant) is treated as excluded.

Travel and Software are only bonus categories when the transaction record shows that posted category. Do not override a posted non-bonus category merely because a merchant sounds like travel or software. Third-party processors and merchant miscoding can affect the result; flag plausible miscoding for investigation rather than silently reclassifying it.

## Procedure

1. After verification, use normal read-only banking tools to retrieve the customer’s credit-card accounts and credit-card transaction history. Keep the raw records available for the review.
2. Create JSON for `scripts/review_rewards.py` from the live records. Include all candidate transactions and the account opening date for each card type. Use decimal strings for monetary amounts when possible.
3. Run the script. It emits an expected rate, expected points, recorded points, point/dollar difference, rule rationale, and a `finding` for each reviewable transaction. It also emits unreviewed records and input/data-quality errors; do not ignore these.
4. Review only `finding: underpaid` entries as possible missing cash back. `matched` means the recorded value agrees with the known rules after point rounding. `overpaid` is a data observation, not an instruction to reverse rewards. `unreviewed` needs more information.
5. Explain results in clear terms: identify the card and transaction date/merchant, purchase amount, recorded rewards in both points and dollars, expected rewards in both points and dollars, difference, and the rule that produced the result. State that points on these cards represent cash back at one cent each.
6. For an apparent shortfall, say it requires a rewards review/correction rather than promising an automatic credit. Collect or retain receipt/invoice details if the customer can provide them, especially where category coding may be wrong. For exclusions or normal-rate purchases, explain the applicable exclusion/base-rate rule.
7. Do not expose unrelated transactions or account information. If the customer names a specific transaction, limit the response to that item unless they request a broader review.

## Script interface

Run with JSON on stdin:

```json
{
  "accounts": [
    {"card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Business Silver Rewards Card",
      "merchant_name": "string",
      "transaction_amount": "0.00",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": 0
    }
  ],
  "silver_base_rate": "0.01"
}
```

`accounts` and `transactions` are required arrays. `silver_base_rate` is optional and defaults to 1%; pass a different known rate only when supported by current card terms. The script writes one JSON object to stdout. It performs no banking calls and makes no account changes.

The Business promotion window is calculated as `[opening date, six-calendar-month anniversary)`. Enrollment is determined from the account opening date, inclusive of the stated promotion start and end dates. This explicit boundary convention should be disclosed if a transaction falls on the anniversary date.

## Validation before communicating results

- Confirm every output transaction has the correct card type and an account belonging to the verified customer.
- Confirm all reviewed records have `status` equal to `COMPLETED`, a valid date, a nonnegative amount, and numeric recorded points.
- Check that points-to-dollars conversions divide by 100 and that displayed money uses two decimal places.
- Check that expected points use half-up rounding to a whole point, matching whole-point database storage.
- Reconcile the number of reviewed, underpaid, matched, overpaid, and unreviewed entries against the script’s `summary`.
- Do not claim a merchant was miscategorized unless the customer supplies evidence or a supported category review determines that it was.
