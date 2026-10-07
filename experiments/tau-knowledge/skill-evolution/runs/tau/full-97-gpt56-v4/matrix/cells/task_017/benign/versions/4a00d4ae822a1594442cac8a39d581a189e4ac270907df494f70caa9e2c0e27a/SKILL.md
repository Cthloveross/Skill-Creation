---
name: silver-rewards-cash-back-dispute-correction
description: Review suspected Silver Rewards Card cash-back errors, independently calculate whole-point rewards, and correct only transactions covered by completed approved cash-back disputes using the authorized internal update tool. Use for a customer who reports incorrect credit-card rewards or for internal resolved-dispute processing.
---

# Silver Rewards cash-back review and correction

## Scope and rules

Use this Skill for **Silver Rewards Card** transactions. Its known rates are:

- **4.0%** for eligible, posted/completed `Travel` and `Software` transactions.
- **1.0%** for purchases outside those categories.
- Rewards are stored and updated as points, where 1 point equals $0.01 cash back.
- Always truncate fractional points down. Never round to nearest.

A transaction may fail enhanced-rate eligibility if its final merchant category is not Travel or Software, or if it is an excluded item (gift card, person-to-person payment, fee, interest, bank-charged insurance premium, return, or refund). Use the posted database category and status, not merchant-name guesses. Do not calculate a final correction for a non-posted transaction.

An actual reward change is permitted only after the associated cash-back dispute is **resolved and approved**. A customer merely noticing a possible error is not evidence of an approved dispute.

## Conversation, lookup, and verification

1. Acknowledge the concern and obtain enough information to locate the account (for example, full name or account email).
2. Before disclosing detailed account/transaction information or making a correction, verify identity by confirming two of the four identity fields: date of birth, email, phone number, and address. Retrieve the customer record, get the current time, and call `log_verification` with every required field and the current timestamp after successful verification.
3. Retrieve the user's credit-card account(s) and transaction history. Ensure the relevant account and each reviewed transaction are a Silver Rewards Card transaction.
4. Locate the user's cash-back dispute records and identify the exact transaction IDs whose disputes are both resolved and approved. This prerequisite is mandatory. If the available runtime has no dispute lookup capability, do not infer approval, do not update rewards, and explain that a correction must wait for the dispute-resolution record or route the case through the supported dispute workflow.
5. Run `scripts/calculate_silver_rewards.py` on the retrieved transactions, passing only the IDs supported by approved dispute records in `approved_transaction_ids`. Review its output before any update.

## Applying a correction

For every item in `approved_updates`:

1. Unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`.
2. Call `update_transaction_rewards_3847` through `call_discoverable_agent_tool`, with exactly:
   ```json
   {"transaction_id":"<exact transaction id>","new_rewards_earned":"<whole-number> points"}
   ```
3. Re-read transaction history and confirm the stored reward value now matches the calculated whole-point result. Do not repeat an update if its outcome is unknown; investigate/escalate instead.
4. Retain the transaction ID, final category/status, rate, amount, truncation calculation, previous value, new value, and dispute approval basis in the internal case record.

Do not update transactions returned under `blocked_discrepancies`: they may be genuine discrepancies, but lack an approved-dispute authorization. Do not rely on any `expected_rewards` value from a dispute record; use it only to identify the transaction and approval state.

When reporting to the customer, state the reviewed posted transaction(s), whether a correction was completed or is pending dispute resolution, and that points represent cents of cash back. Avoid exposing unrelated transaction details.

## Calculator interface

`python3 scripts/calculate_silver_rewards.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "transaction_amount": "$12.34 or 12.34",
      "category": "Travel|Software|...",
      "status": "COMPLETED|POSTED|...",
      "rewards_earned": "123 points or 123"
    }
  ],
  "approved_transaction_ids": ["transaction-id"],
  "excluded_categories": ["optional category labels"]
}
```

`approved_transaction_ids` must contain only exact IDs from resolved, approved dispute records. It may be omitted or empty to perform a review without authorizing any update. The script returns calculated results, all detected discrepancies, approved updates, and discrepancies blocked by missing approval. Invalid money, missing IDs, or missing required transaction fields cause a JSON error and a nonzero exit.

Example runnable call (illustrative values only):

```sh
printf '%s' '{"transactions":[{"transaction_id":"example","transaction_amount":"10.99","category":"Travel","status":"COMPLETED","rewards_earned":"43 points"}],"approved_transaction_ids":["example"]}' | python3 scripts/calculate_silver_rewards.py
```

Validate that each `approved_updates[].new_rewards_earned` equals `floor(amount × applicable_rate × 100)` and is formatted as `<integer> points`, then validate it against the re-read transaction record after the internal update tool succeeds.
