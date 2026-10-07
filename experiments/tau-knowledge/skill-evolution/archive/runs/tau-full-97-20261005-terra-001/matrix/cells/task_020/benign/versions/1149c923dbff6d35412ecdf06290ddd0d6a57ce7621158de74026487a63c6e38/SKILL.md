---
name: cash-back-rewards-discrepancy-review
version: 1.0.0
description: Review posted Business Silver Rewards Card and Silver Rewards Card transactions for cash-back discrepancies, calculate whole-point expected rewards, explain eligibility and exclusions, and safely route eligible corrections through the required dispute process.
---

# Cash-back rewards discrepancy review

Use this Skill when a customer asks to review cash back on one or both Silver Rewards card variants, or when an approved cash-back dispute requires an independently calculated rewards correction.

## Safety and prerequisites

1. **Verify the customer before disclosing account-specific transaction or rewards information.** Obtain confirmation of any two of date of birth, email, phone number, and address against the customer record. Then call `log_verification` with all required fields and a current timestamp. A name alone, an account lookup, or a prior unverified conversation is not sufficient.
2. Retrieve the customer's credit-card accounts and transaction history using the normal banking tools. Do not rely on a customer-supplied calculation, an account reward balance, or an `expected_rewards` field from a dispute record.
3. Analyze only posted/completed purchase transactions. Do not treat authorizations, refunds, returns, credits, fees, interest, gift cards, person-to-person payments, insurance premiums, or unknown statuses as qualifying rewards purchases. Explain when a category is unknown or a transaction cannot be calculated from the available data.
4. All calculated values are **points**, although these cards are cash-back cards. One point represents $0.01. Calculate the total correct whole-point value, not merely an adjustment delta.

## Rules implemented by the analyzer

- **Business Silver Rewards Card:** 10% on eligible travel or software and 1% otherwise.
- **Silver Rewards Card:** 4% on eligible travel or software and 1% otherwise.
- Eligibility depends on the merchant-submitted travel/software category. Direct provider booking is helpful but does not override the recorded merchant category.
- For Business Silver, the named exclusion brands (including Microsoft and Coursera) receive the standard rate even when categorized as software or travel.
- The Business Silver double-cash-back offer applies only if the account opened from 2024-11-14 through 2025-11-14, inclusive. It doubles the otherwise applicable rate for purchases dated from the account-opening date up to, but not including, the same calendar day six months later. Exclusions still receive the doubled standard rate during this period.
- Floor fractional points for **each transaction**. Do not round, aggregate fractional points across purchases, or calculate a cash-dollar amount first.

## Run the calculation

Save account and transaction fields obtained at runtime into JSON and run:

```text
python scripts/analyze_rewards.py <<'JSON'
{
  "accounts": [{"card_type": "...", "date_of_account_open": "YYYY-MM-DD"}],
  "transactions": [{
    "transaction_id": "...",
    "credit_card_type": "...",
    "merchant_name": "...",
    "transaction_amount": "...",
    "transaction_date": "YYYY-MM-DD",
    "category": "...",
    "status": "COMPLETED",
    "rewards_earned": "... points"
  }]
}
JSON
```

The script reads one JSON object from stdin and emits one JSON object to stdout. `accounts` and `transactions` are required arrays. Amounts may be numeric or dollar-formatted strings; rewards may be an integer or a string such as `"123 points"`. Dates must be ISO `YYYY-MM-DD` (a timestamp beginning with that date is accepted).

The result contains:

- `reviews`: one record per usable transaction, including the expected whole points, recorded points when supplied, difference (`expected - recorded`), selected rate, and rule rationale.
- `discrepancies`: only records where recorded and expected points differ.
- `not_reviewed`: records skipped due to missing data, unsupported cards/categories, or non-posted status.
- `validation`: machine-readable checks confirming expected values are whole nonnegative points and that reviewed transaction IDs are unique.

Review `not_reviewed` before representing the review as complete. Treat a nonempty `validation.errors` as a failed calculation and correct the source data rather than using its recommendations.

## Communicate the review

Explain each discrepancy in customer-friendly terms: the posted amount in points and cash equivalent, the expected amount in points and cash equivalent, and the relevant rate, promotion, category, or exclusion. Do not promise a credit merely because the calculation differs; merchant classification and dispute review may still be required.

If a transaction seems miscoded, ask for the receipt or confirmation when available. Useful dispute context is the transaction date, merchant, amount, recorded versus expected rewards, and supporting receipt. The customer may identify a subset of findings if they do not want to dispute every discrepancy.

## Submit a customer dispute

The customer, not the agent, initiates a cash-back discrepancy review. Confirm the exact transaction ID, then provide `submit_cash_back_dispute_0589` through `give_discoverable_user_tool` with the customer's own `user_id` and that transaction ID. Provide one tool invocation per transaction the customer chooses to dispute. Supporting context can be requested later in review.

Do not submit a dispute on the customer's behalf and do not collect card numbers or other unnecessary sensitive card details.

## Apply a correction only after approval

This section is for internal post-resolution work, not the initial review.

1. Retrieve the user's dispute history with `get_user_dispute_history_7291` when that tool is available in the runtime. If it is unavailable, do not invent a substitute or update any transaction; use the normal internal escalation path.
2. Select only disputes that are resolved/approved and identify their exact transaction IDs. An open, under-review, rejected, or ambiguous dispute must not be corrected.
3. Re-run `scripts/analyze_rewards.py` using the source account and transaction data. Independently verify the category, exclusion, transaction date, account opening date, applicable promotion, and floor rounding. Never rely on a dispute record's expected-rewards value.
4. Unlock `update_transaction_rewards_3847` using `unlock_discoverable_agent_tool` and call it through `call_discoverable_agent_tool` with the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`, where `X` is the analyzer's `expected_points` integer.
5. Re-read transaction history and confirm the updated stored value equals `X points`. Retain the calculation rationale and approval linkage in the normal internal case record.

Never call the update tool for a skipped, non-completed, unapproved, or validation-failed transaction.
