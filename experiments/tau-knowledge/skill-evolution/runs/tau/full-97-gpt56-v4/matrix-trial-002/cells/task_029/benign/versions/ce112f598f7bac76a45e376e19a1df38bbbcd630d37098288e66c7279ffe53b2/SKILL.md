---
name: crypto-cash-back-reward-review
description: Safely verify a customer's identity, review completed Crypto-Cash Back purchase rewards against the documented 2.0% rate and whole-point truncation rule, and initiate the customer-facing cash-back dispute path for any discrepancy. Use when a customer asks to check potentially incorrect card rewards.
---

# Crypto-Cash Back Reward Review

## Scope and governing rules

Use the calculation portion of this Skill for **Crypto-Cash Back** transactions only. The cash-back dispute submission path itself can be used for any credit-card transaction once the customer has supplied and confirmed its transaction ID. The available Crypto-Cash Back policy establishes:

- Eligible Crypto-Cash Back purchases earn **2.0%**.
- Cash-back-card database `points` represent cash back at **100 points per dollar**.
- Rewards are always rounded **down** to a whole point.
- Therefore, for an eligible completed Crypto-Cash Back purchase, expected points are:

  `floor(transaction_amount_in_dollars * 2)`

Do not infer rates for other card types from their transaction history. Do not assume a transaction is eligible where its category is `Other`, unknown, or where the record is not a completed purchase. Explain that such records require review rather than declaring a discrepancy. The standard calculator does not establish an unprovided promotional rate: if the transaction or dispute indicates a promotion, verify the promotion applicable on the purchase date before calling a standard-rate result a discrepancy or using it for a correction.

A review does not authorize an agent to change rewards. A customer must submit a dispute for a specific transaction using the designated customer-facing tool. An internal reward correction is permissible only after a dispute has been resolved and approved.

## Required interaction workflow

1. **Identify the customer.** If no reliable account identifier is already available, request their exact full name, account email, or user ID, then use the corresponding user lookup tool.
2. **Verify identity before discussing account-specific results.** Ask the customer to confirm any two of date of birth, email, phone number, and address. Compare their responses to the user record. If two match, obtain the current timestamp and call `log_verification` with every required field from the record, the name/user ID, and that timestamp. Do not disclose account or transaction details if verification fails or is incomplete.
3. **Get the records.** Call `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` for the verified user. Confirm whether a Crypto-Cash Back account exists. If it does not, do not apply the Crypto rate or calculator; a customer may still use the general dispute action for a specific confirmed transaction.
4. **Review only supported transactions.** Send the transaction records to `scripts/review_crypto_rewards.py`. Supply the exact transaction fields returned by the system; do not type expected rewards into the input.
5. **Explain the outcome.** State the documented rate, the floor-to-whole-point rule, and, for each supported mismatch, the transaction identifier, date/merchant/amount as appropriate, recorded points, and independently calculated expected points. State that the review is limited to Crypto-Cash Back because no other card rates are established by this Skill.
6. **Offer the dispute action for each supported mismatch.** Use `give_discoverable_user_tool` with `discoverable_tool_name` set to `submit_cash_back_dispute_0589` and `arguments` set to a JSON string containing the verified user's `user_id` and that exact `transaction_id`. The customer executes it themselves. Confirm the transaction ID before providing the tool. This submission process applies to all credit-card transactions: for a non-Crypto card whose rate is not established here, do not calculate or assert a mismatch, but provide the same customer-facing dispute action if the customer identifies and confirms a transaction they want reviewed.
7. **Correct only an approved, resolved dispute.** Identify the affected IDs by looking up the verified user's resolved disputes in the `cash_back_disputes` database when that lookup is available. Do not use a dispute record's `expected_rewards` field as the calculation. In a runtime that does not expose that lookup, use only an explicit approved-and-resolved status supplied by the current case workflow for the exact transaction; never invent a database tool or assume a pending/denied dispute is approved. Independently recalculate the correct result from the card type, transaction category, eligibility, any promotion applicable on the purchase date, and whole-point rule; do not assume a promotion where none is established. Unlock `update_transaction_rewards_3847` and invoke it only for each approved transaction with `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`. Retrieve `get_credit_card_transactions_by_user` afterward and confirm the corrected value in transaction history. Retain the independent calculation notes in the internal case record. If approval and resolution for the exact transaction cannot be established, do not update it.

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
