---
name: crypto-cash-back-reward-review
description: Safely verify a customer's identity, review completed Crypto-Cash Back purchase rewards against the documented 2.0% rate and whole-point truncation rule, and initiate the customer-facing cash-back dispute path for any discrepancy. Use when a customer asks to check potentially incorrect card rewards.
---

# Crypto-Cash Back Reward Review

## Scope and governing rules

Use this Skill for **Crypto-Cash Back** transactions only. The available policy establishes:

- Eligible Crypto-Cash Back purchases earn **2.0%**.
- Cash-back-card database `points` represent cash back at **100 points per dollar**.
- Rewards are always rounded **down** to a whole point.
- Therefore, for an eligible completed Crypto-Cash Back purchase, expected points are:

  `floor(transaction_amount_in_dollars * 2)`

Do not infer rates for other card types from their transaction history. Do not assume a transaction is eligible where its category is `Other`, unknown, or where the record is not a completed purchase. Explain that such records require review rather than declaring a discrepancy.

A review does not authorize an agent to change rewards. A customer must submit a dispute for a specific transaction using the designated customer-facing tool. An internal reward correction is permissible only after a dispute has been resolved and approved.

## Required interaction workflow

1. **Identify the customer.** If no reliable account identifier is already available, request their exact full name, account email, or user ID, then use the corresponding user lookup tool.
2. **Verify identity before discussing account-specific results.** Ask the customer to confirm any two of date of birth, email, phone number, and address. Compare their responses to the user record. If two match, obtain the current timestamp and call `log_verification` with every required field from the record, the name/user ID, and that timestamp. Do not disclose account or transaction details if verification fails or is incomplete.
3. **Get the records.** Call `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` for the verified user. Confirm that a Crypto-Cash Back account exists.
4. **Review only supported transactions.** Send the transaction records to `scripts/review_crypto_rewards.py`. Supply the exact transaction fields returned by the system; do not type expected rewards into the input.
5. **Explain the outcome.** State the documented rate, the floor-to-whole-point rule, and, for each supported mismatch, the transaction identifier, date/merchant/amount as appropriate, recorded points, and independently calculated expected points. State that the review is limited to Crypto-Cash Back because no other card rates are established by this Skill.
6. **Offer the dispute action for each mismatch.** Use `give_discoverable_user_tool` with `discoverable_tool_name` set to `submit_cash_back_dispute_0589` and `arguments` set to a JSON string containing the verified user's `user_id` and that exact `transaction_id`. The customer executes it themselves. Confirm the transaction ID before providing the tool.
7. **Do not apply a correction now.** If a future approved dispute requires a correction, follow the separate approved-dispute procedure: locate the resolved dispute, independently recalculate its rate and eligibility, unlock `update_transaction_rewards_3847`, update it with a string such as `"123 points"`, and confirm the transaction history afterward.

## Calculator script

Run `scripts/review_crypto_rewards.py` with JSON on stdin. It emits JSON on stdout.

### Input schema

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Crypto-Cash Back",
      "transaction_amount": "$12.34 or 12.34",
      "category": "Shopping",
      "status": "COMPLETED",
      "rewards_earned": "24 points or 24"
    }
  ]
}
```

Extra source fields, such as merchant and date, are retained in the script output when present. The script accepts either numeric or formatted currency/point strings. It rejects missing or malformed required calculation fields rather than silently estimating.

### Output interpretation

- `mismatches` contains supported completed Crypto-Cash Back purchases where recorded and expected whole points differ.
- `matches` contains supported records that reconcile.
- `needs_manual_review` contains Crypto-Cash Back records outside the calculation assumptions (not completed, `Other`/unknown category, or invalid/missing fields).
- `ignored_non_crypto` reports transactions belonging to other cards; these must not be analyzed using the Crypto rate.
- `errors` means the affected record should not be used to make a rewards conclusion.

Before communicating results, ensure every mismatch has a nonempty transaction ID and that expected points are a nonnegative integer. Do not provide the dispute tool for a malformed record.
