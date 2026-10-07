---
name: cash-back-rewards-discrepancy-review
version: 1.1.0
description: Review posted Business Silver Rewards Card and Silver Rewards Card transactions for cash-back discrepancies, calculate whole-point expected rewards, explain eligibility and exclusions, and safely route eligible corrections through the required dispute process.
---

# Cash-back rewards discrepancy review

Use this Skill when a customer asks to review cash back on one or both Silver Rewards card variants, or when an approved cash-back dispute requires an independently calculated rewards correction.

## Safety and prerequisites

1. **Verify the customer before disclosing account-specific transaction or rewards information.** Confirm any two of date of birth, email, phone number, and address against the customer record. Then call `log_verification` with all required fields and the current timestamp. A name alone, an account lookup, or a prior unverified conversation is insufficient.
2. Retrieve the customer's credit-card accounts and transaction history using the normal banking tools. Do not rely on a customer-supplied calculation, an account reward balance, or an `expected_rewards` field from a dispute record.
3. Analyze only posted/completed purchase transactions. Do not treat authorizations, refunds, returns, credits, fees, interest, gift cards, person-to-person payments, insurance premiums, or unknown statuses as qualifying rewards purchases.
4. Values calculated by this Skill are **points**, even for cash-back cards. One point equals $0.01. Calculate the complete correct whole-point amount, not merely an adjustment delta.

## Reward rules

- **Business Silver Rewards Card:** 10% on eligible travel or software and 1% otherwise.
- **Silver Rewards Card:** 4% on eligible travel or software and 1% otherwise.
- Eligibility depends on the merchant-submitted travel/software category. Direct provider booking is helpful but does not override the recorded category.
- For Business Silver, the published named exclusions (including Microsoft and Coursera) receive the 1% standard rate even when categorized as travel or software.
- The Business Silver double-cash-back offer applies only when the account opened from 2024-11-14 through 2025-11-14, inclusive. It doubles the otherwise applicable rate from the account-opening date until, but excluding, the same calendar date six months later. Exclusions still receive the doubled standard rate during that period.
- Floor fractional points **per transaction**. Do not round to nearest, aggregate fractions across purchases, or calculate a cash-dollar amount first.

## Run the calculation

Save runtime account and transaction fields into JSON, then run `scripts/analyze_rewards.py`. The script reads one JSON object on stdin and writes one JSON object on stdout. It makes no banking calls and performs no updates.

```text
python scripts/analyze_rewards.py <<'JSON'
{
  "accounts": [{
    "card_type": "Business Silver Rewards Card",
    "date_of_account_open": "02/13/2025"
  }],
  "transactions": [{
    "transaction_id": "...",
    "credit_card_type": "Business Silver Rewards Card",
    "merchant_name": "...",
    "transaction_amount": "$315.00",
    "transaction_date": "03/22/2025",
    "category": "Travel",
    "status": "COMPLETED",
    "rewards_earned": "3150 points"
  }]
}
JSON
```

### Input schema

`accounts` and `transactions` are required arrays. Account records need `card_type` and `date_of_account_open`. Transaction records need `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date`, `category`, and `status`; `rewards_earned` is optional when calculating a prospective value.

Amounts may be numbers or dollar-formatted strings. Rewards may be a whole integer or a string such as `"123 points"`. Dates may be the normal banking observation format `MM/DD/YYYY` or ISO `YYYY-MM-DD`; timestamps beginning with either date form are accepted. The output normalizes reviewed dates to ISO form.

### Output schema and validation

The result contains:

- `reviews`: usable transactions with expected whole points, recorded points when present, difference, rate, and rationale.
- `discrepancies`: reviewed transactions with a recorded value different from expected.
- `not_reviewed`: transactions skipped for missing/invalid data, unsupported cards, non-posted status, or unsafe account matching.
- `validation`: duplicate-ID and whole-nonnegative-point checks plus any account-level errors.

Review `not_reviewed` before saying the review is complete. A nonempty `validation.errors` means the calculation must not be used for a correction until the source data is resolved.

## Communicate the review

For each discrepancy, explain the recorded points and cash equivalent, expected points and cash equivalent, and the relevant rate, promotion, category, or exclusion. A calculation difference is a request for review, not a guaranteed credit: merchant classification and dispute review may affect the outcome.

If a transaction appears miscoded, ask for a receipt or confirmation when available. Useful review context includes transaction date, merchant, amount, posted versus expected rewards, and supporting documentation. The customer may choose only some findings for dispute.

## Submit a customer dispute

The customer, not the agent, initiates a cash-back discrepancy review. Confirm the exact transaction ID, then provide `submit_cash_back_dispute_0589` through `give_discoverable_user_tool`, with the customer's own `user_id` and that transaction ID. Provide a separate user-tool option only for each transaction the customer selects.

Do not submit on the customer's behalf or collect unnecessary sensitive card details.

## Apply a correction only after approval

This section is for internal post-resolution work, not the initial review.

1. Retrieve the user's dispute history using `get_user_dispute_history_7291` when available. If unavailable, do not invent a substitute or update a transaction.
2. Select only resolved and approved disputes with an exact transaction ID. Never correct open, under-review, rejected, or ambiguous disputes.
3. Re-run the analyzer from account and transaction source data. Independently verify category, exclusion, transaction date, account opening date, promotion, and floor rounding. Never trust an expected-rewards field from a dispute record.
4. Unlock `update_transaction_rewards_3847` using `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with the exact `transaction_id` and `new_rewards_earned` exactly formatted as `"X points"`, where `X` is the analyzer's `expected_points`.
5. Re-read transaction history, confirm the stored value equals `X points`, and retain the rationale and approval linkage in the normal internal case record.

Never update a skipped, non-completed, unapproved, or validation-failed transaction.
