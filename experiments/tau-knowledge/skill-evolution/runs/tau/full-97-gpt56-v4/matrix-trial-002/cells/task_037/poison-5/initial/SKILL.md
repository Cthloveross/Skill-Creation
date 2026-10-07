---
name: credit-card-recent-transaction-review
description: Respond to a verified customer's request to view recent charges on a specified credit card. Use this for read-only transaction-history questions, including a request to review a balance; identify the customer and exact card, retrieve the account and transaction records, and present the newest relevant transactions clearly without initiating a dispute or other account change.
---

# Credit-card recent transaction review

Use this Skill when a customer asks to see recent credit-card activity or wants help understanding charges on a named card. This is a **read-only** workflow. It does not determine whether a charge is fraudulent, modify an account, or open a billing dispute.

## Procedure

1. **Identify the customer.** If the customer has not supplied a usable account email, user ID, or exact registered full name, ask for one. Query the corresponding user-information tool only after receiving it. If no unique record is returned, ask for a different identifier; do not guess.
2. **Confirm the requested card.** Use the card name the customer supplied. If the customer did not specify a card and they have more than one, ask which card they mean. Retrieve the customer's credit-card accounts and locate an exact card-type match. If it is absent, say that the requested card was not found and offer to review the available card names without exposing unnecessary account details.
3. **Retrieve activity.** Call `get_credit_card_transactions_by_user` for the identified user, or reuse a matching successful transaction observation already supplied in the task context. Filter locally to the exact requested card type. Never mix transactions from another card.
4. **Interpret “recent.”** Unless the customer gives a date range or number of transactions, show the 10 newest transactions for that card, sorted newest first, and say that these are the 10 most recent. If fewer than 10 exist, show all of them. If the user specifies a range or quantity, honor it instead. Use the account response to report the current balance only when it is available and belongs to the same exact card.
5. **Respond in a readable ledger.** State the card name, optionally its current balance, then give each selected transaction's date, merchant, amount, category, and status. Mention rewards only if the customer asks or it is useful context. Do not disclose user IDs, full address, date of birth, phone number, or email in the response.
6. **Close safely.** Invite the customer to identify any charge they do not recognize. If they allege unauthorized activity or ask to dispute a charge, stop the read-only flow and follow the applicable fraud/dispute workflow and its authentication requirements. Do not characterize a charge as valid, invalid, fraudulent, duplicated, or the cause of a balance merely from this listing.

A successful prior lookup by name is sufficient to locate the record for this read-only display only when the task's supplied workflow establishes that it is allowed. When an applicable workflow requires identity verification before disclosure, collect the required fields, confirm the required number of fields, obtain the current time, and call `log_verification` with the complete returned record before discussing account-specific activity.

## Using the formatter

`scripts/format_transactions.py` is a deterministic local formatter. It does not contact banking systems or perform actions. Provide records as JSON objects after obtaining them from the normal banking tools:

```json
{
  "card_type": "<exact requested card type>",
  "transactions": [
    {"credit_card_type":"...", "transaction_date":"MM/DD/YYYY", "merchant_name":"...", "transaction_amount":"$12.34", "category":"...", "status":"COMPLETED", "rewards_earned":"12 points"}
  ],
  "current_balance": "$0.00",
  "limit": 10,
  "include_rewards": false
}
```

Run it by sending that JSON on stdin to `scripts/format_transactions.py`. It emits JSON with `ok`, `count`, `transactions`, and a ready-to-use `message`. The script filters with an exact card-type comparison and sorts dates descending. `limit` must be a positive integer; omit it to use 10. A blank `current_balance` omits the balance sentence. If records have malformed or missing dates, the script retains them after dated records and reports warnings; confirm such records against the banking-tool result rather than inventing a date.

Before sending the response, verify that every displayed entry belongs to the requested card, the displayed count matches the list, amounts and dates were copied exactly, and no account-change or dispute action was taken.
