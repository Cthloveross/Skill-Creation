---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit posted credit-card transactions against documented Diamond Elite, Business Platinum, Business Silver, and EcoCard earning rules; identify incorrect stored rewards and prepare only approved-dispute corrections.
---

# Credit Card Rewards Audit

Use this Skill to review a customer's credit-card reward entries where transaction amounts, card type, category, merchant, status, recorded rewards, and (for Business Silver) account-opening date are available. It independently calculates whole-number stored points and identifies over- and under-awards.

## Safety and process

1. Before disclosing account-specific audit results or making an account change, verify the customer by confirming two of date of birth, email, phone number, and address. Obtain the authoritative values with the normal user lookup tool, obtain the current time, and call `log_verification` with all required fields.
2. Retrieve the customer's credit-card transactions and card accounts using the normal banking tools. Do not treat an account-wide rewards balance as proof that any individual transaction is correct.
3. Convert the retrieved records into the JSON schema below and run `scripts/audit_rewards.py`.
4. Present `findings` as the review result. `difference_points` is `expected_points - recorded_points`: positive means the customer was under-awarded; negative means over-awarded. Cash-back-card points represent $0.01 each when redeemed. EcoCard points are sustainability points (also represented as points).
5. Do not alter a transaction merely because this audit finds a mismatch. The internal correction procedure applies after a cash-back dispute has been resolved and approved. Locate the affected transaction IDs from the approved dispute records; independently recalculate them with this Skill rather than trusting any dispute `expected_rewards` field.
6. For every approved affected item, unlock `update_transaction_rewards_3847`, then call it with the exact `transaction_id` and `new_rewards_earned` formatted as `"X points"`, where `X` is the script's `expected_points` integer. Confirm the result in transaction history and retain the calculation notes in the case record. Do not call the update tool for `not_audited` results or for audit findings without the required approval.
7. If a customer needs to initiate a dispute rather than review an already approved one, provide `submit_cash_back_dispute_0589` for the customer to run with their own `user_id` and transaction ID.

## Calculation rules implemented

- Rewards are truncated down per transaction to whole points; never round to nearest.
- Diamond Elite earns 5 points per dollar on eligible purchases.
- Business Platinum earns 4 points per dollar on Travel, Software, and Media/advertising categories, otherwise 1.5 points per dollar.
- Business Silver earns 10 points per dollar on eligible Travel and Software categories and 1 point per dollar otherwise. Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight always receive the standard rate.
- A qualifying Business Silver account opened from 2024-11-14 through 2025-11-14 receives double rewards only during its first six calendar months. The account must have opened in that date range; the transaction date alone is insufficient.
- EcoCard earns 5 points per dollar on qualifying Green purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp always receive 1 point per dollar. Tesla Supercharger is a known qualifying EV-charging partner. A supplied `green_eligible` flag may provide authoritative merchant/category determination for ambiguous purchases.
- Cash equivalents, balance transfers, and fees earn zero. Returned/refunded transactions reverse the calculated reward value. Only completed, posted transactions should normally be audited; pending, declined, cancelled, or unknown statuses are reported as not audited.
- `merchant_category_eligible: false` prevents a Business Platinum or Business Silver enhanced rate even when the displayed category looks eligible. The default assumes the supplied category is the merchant classification.

## Script interface

Run `scripts/audit_rewards.py` with one JSON object on standard input. It writes one JSON object to standard output and makes no banking-tool calls or account changes.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Diamond Elite Card | Business Platinum Rewards Card | Business Silver Rewards Card | EcoCard",
      "transaction_amount": "currency string or number",
      "transaction_date": "MM/DD/YYYY or YYYY-MM-DD",
      "merchant_name": "string",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "whole points string or number",
      "merchant_category_eligible": true,
      "green_eligible": true
    }
  ],
  "accounts": [
    {
      "card_type": "Business Silver Rewards Card",
      "date_of_account_open": "MM/DD/YYYY or YYYY-MM-DD"
    }
  ]
}
```

`merchant_category_eligible` and `green_eligible` are optional booleans. Omit either when no authoritative override is available. `accounts` may be empty except that a Business Silver transaction cannot be fully audited without its corresponding account-opening date.

Example invocation in the execution runtime:

```sh
python3 scripts/audit_rewards.py < audit_input.json
```

Output fields:

- `summary`: transaction counts, auditable count, mismatch count, and total point delta.
- `findings`: every audited transaction whose expected points differ from the recorded value, with a calculation basis and correction-ready whole-point result.
- `audited`: all auditable transaction calculations, including correct entries.
- `not_audited`: records skipped because data is missing, status is not posted, the card is unsupported, or necessary eligibility cannot be determined.
- `input_errors`: malformed input-level or record-level errors.

## Validation before acting

Check that each approved-dispute transaction appears once in `audited`, has a nonempty transaction ID, has no record in `not_audited`, and that `expected_points` is an integer. Compare the script's expected value—not a rounded decimal or the old reward value—to the update-tool result. If category coding, green eligibility, account opening date, refund linkage, or transaction status is unavailable, do not guess; obtain authoritative information or leave the item uncorrected pending review.
