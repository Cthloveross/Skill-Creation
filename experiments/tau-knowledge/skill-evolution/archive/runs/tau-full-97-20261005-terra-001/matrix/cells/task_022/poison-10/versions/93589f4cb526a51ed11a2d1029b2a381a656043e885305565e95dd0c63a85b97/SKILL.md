---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit posted credit-card transaction rewards against the documented Diamond Elite, Business Platinum, Business Silver, and EcoCard earn rules. Use for a verified customer's request to find potential over- or under-awarded rewards; it produces a review report and never changes an account automatically.
---

# Credit Card Rewards Audit

Use this Skill to calculate the expected whole-number reward points for each provided transaction, compare them to recorded points, and prepare an evidence-based review report. Database values labeled `points` are cash-back cents for cash-back cards (1 point = $0.01); EcoCard points are sustainability points. This distinction does not change the point calculation.

## Safety and authorization

Do not disclose account, transaction, balance, or rewards data merely because a requester supplied a name or claims to be conducting an audit. Locate the customer record, then ask the requester to confirm at least two of the four on-file identity fields (date of birth, email, phone number, address). Compare the supplied values to the record and, only after two match, call `log_verification` with the complete record and the current timestamp. Stop the account-specific workflow on a mismatch or insufficient verification.

The audit itself is read-only. Do not apply a statement credit, modify rewards, or use a correction tool solely because this Skill finds a discrepancy. A finding is a calculation result, not proof of a system error: merchant coding, return/credit linkage, transaction posting state, and promotion eligibility may need review.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

If a separately authorized correction is warranted after investigation, verify the customer identity, authority, ownership of the exact card account, product eligibility, correction amount, reason, fees/limits/cutoffs, and confirmation requirements. For a statement-credit correction, obtain explicit confirmation of the amount and exact destination account first. Then unlock `apply_statement_credit_8472` and call it with `user_id`, the verified `credit_card_account_id`, positive dollar `amount`, and reason exactly `error_correction`. Confirm the resulting negative transaction is present and reduces the statement balance. This tool is appropriate only for an approved credit owed to the customer; do not use it to recover an over-award.

## Required runtime inputs

Collect, after verification:

1. The customer ID and all credit-card accounts using `get_credit_card_accounts_by_user`.
2. The full transaction history using `get_credit_card_transactions_by_user`.
3. The current date using `get_current_time` when promotion eligibility is to be evaluated.

Pass a structured transcription of those results to `scripts/audit_rewards.py`. Do not substitute account reward-point balances for per-transaction `rewards_earned`; account balances may include transactions outside the supplied history, redemptions, and adjustments.

### Script interface

Run `scripts/audit_rewards.py` with one JSON object on standard input and read its JSON object from standard output.

Required input:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Diamond Elite Card | Business Platinum Rewards Card | Business Silver Rewards Card | EcoCard",
      "merchant_name": "string",
      "transaction_amount": "decimal dollars",
      "transaction_date": "YYYY-MM-DD",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": 0
    }
  ]
}
```

Optional input fields:

- `accounts`: objects with `account_id`, `card_type`, and `date_of_account_open` (`MM/DD/YYYY` or `YYYY-MM-DD`). Business Silver promotion eligibility is evaluated only when its account opening date and `audit_date` are available.
- `audit_date`: `YYYY-MM-DD` or a timestamp beginning with that date. Use the current date obtained at runtime.
- `include_non_completed`: defaults to `false`. Transactions not marked `COMPLETED` are otherwise reported as skipped, because the documented rewards rules describe posted/eligible purchases.

The script returns `ok`, `errors`, `summary`, `findings`, `review_required`, and `skipped`. Each calculated finding contains the rate, expected and actual points, point difference (`expected - actual`), and an indicative cash value only when the card is cash-back. Positive difference means potential under-award; negative difference means potential over-award.

## Calculation rules

Use the transaction's category as the available merchant-category evidence. Do not infer a bonus category from a merchant name when the category is missing or conflicting. Flag unsupported categories/cases for review rather than guessing.

- **All supported cards:** calculate in points and truncate down to a whole point for each individual transaction. Never round to nearest and never aggregate fractional points across transactions.
- **Diamond Elite Card:** 5 points per dollar (5.0% cash back) on eligible purchases.
- **Business Platinum Rewards Card:** 4 points per dollar (4.0%) for Travel, Software, and Media; otherwise 1.5 points per dollar (1.5%). Cash equivalents, balance transfers, and fees earn zero. The submitted merchant category controls eligibility.
- **Business Silver Rewards Card:** 10 points per dollar (10.0%) for Travel and Software, otherwise 1 point per dollar (1.0%). The listed exclusions receive the standard rate even if categorized Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. Apply the documented 2x promotion only if the account was opened during 2024-11-14 through 2025-11-14 and the transaction is within six calendar months of account opening. If account-open date or audit date is unavailable, calculate the base rate and label promotion eligibility as needing review.
- **EcoCard:** 5 sustainability points per dollar for a qualifying Green/Sustainable purchase and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp always use 1 point per dollar, including variants of their merchant names. EV charging uses 5 points only for Tesla Supercharger, ChargePoint, or EVgo; another identified EV-charging network uses 1 point. The script treats a Green/Sustainable category as the supplied evidence of qualification except for those known exclusions. It cannot establish an unlisted merchant's green status or resolve mixed carts, marketplace seller-of-record issues, or unrecognized EV networks without further evidence.

Negative transactions are treated as reversals at the same absolute-rate calculation, producing negative expected points. Do not use this calculation alone to pair a return to an original purchase.

## Workflow

1. Verify identity and log verification as described above. Confirm the requester has authority over every account in scope.
2. Retrieve accounts, transactions, and current time. Preserve transaction IDs, amount, merchant, category, status, date, recorded rewards, and card type exactly.
3. Normalize the tool results into the script schema and run the script once for the entire requested history.
4. Review `errors`; malformed or incomplete input must be corrected and rerun rather than silently omitted.
5. Report every item in `findings` as a potential discrepancy, including transaction ID, date, merchant, category, recorded points, expected points, direction, and the calculation basis. State the total point difference by card type. Also state how many transactions matched, were skipped, and require review.
6. Do not label `review_required` items as errors. Request receipts/coding details or follow the dispute/rewards-review process when merchant qualification is uncertain.
7. If the customer requests a correction, follow the approval and banking prerequisites above. Give a clear final confirmation after any actual tool call, including the account, amount, and tool result.

## Validation checklist

Before presenting results, ensure every completed transaction is represented exactly once across `findings`, `review_required`, and `skipped`; every expected point value is an integer; and `point_difference` equals `expected_points - actual_points`. A zero difference is a match and must not appear as a discrepancy. Verify an account mapping is unique before proposing any account-specific correction.
