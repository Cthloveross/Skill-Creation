---
name: credit-card-transaction-review
description: Retrieve and clearly present transactions for one customer-selected credit card, then safely triage any unfamiliar or incorrect charge. Use for requests to view recent credit-card activity, investigate a higher-than-expected balance, or identify a transaction for a possible dispute.
---

# Credit Card Transaction Review

## Scope and safety

This Skill supports a read-only transaction review. It does not create disputes, change account data, or assert that a charge is fraudulent or duplicated. Do not expose transactions from cards other than the card the customer requested, and do not expose unrelated profile fields.

Reuse any reliable user lookup, card-account lookup, transaction lookup, and current-time result already supplied in the conversation. Do not repeat a lookup merely because it is available.

A name or email can be used to locate a record using the corresponding lookup tool. Treat it as an account-location identifier, not as completion of identity verification. If an operating workflow requires verification, collect and confirm two of the four available identity fields (date of birth, email, phone number, address), then call `log_verification` with the returned profile values and a current timestamp. Never log a verification when two fields were not actually confirmed.

## Procedure

1. **Identify the customer and requested card.**
   - If the customer has already supplied a name or email and a lookup result is available, use that result's `user_id`.
   - Otherwise, ask for the account name or email, then call `get_user_information_by_name` (names are case-sensitive) or `get_user_information_by_email`.
   - Call `get_credit_card_accounts_by_user` if the requested card has not already been resolved. Match the requested card name against `card_type` exactly after removing only accidental leading/trailing whitespace.
   - If no account matches, say that card could not be located and ask the customer to confirm its name. If multiple cards match, ask which account/card they mean. Never silently choose one.

2. **Retrieve and isolate activity.**
   - Call `get_credit_card_transactions_by_user` with the resolved `user_id` unless a current result is already available.
   - Retain only records whose `credit_card_type` is the resolved card's `card_type`. Do not mix in transactions from the customer's other cards.
   - Sort the retained records by transaction date, newest first. The packaged formatter can perform this deterministically from the raw transaction-tool result.

3. **Give a useful review response.**
   - Confirm the selected card and state its returned current balance, if an account result provided one. Describe it as the *current balance returned by the account lookup*; do not claim it equals the displayed transaction total because prior activity, payments, credits, and statement timing may affect it.
   - Show every matching transaction when the list is reasonably sized. If there are many, show the newest 10 first and explicitly offer the remainder or a requested date range.
   - For each displayed transaction, include date, merchant, amount, and status. Category may be included when available. Include the transaction ID when the customer needs to identify a particular charge, but do not make it the only identifier.
   - If no matching transactions are returned, say so plainly and offer to review a different card or date range. Do not invent transactions or infer a missing charge.
   - Do not label similarly named or similarly priced transactions as duplicates without the customer's confirmation. Invite the customer to identify any merchant, date, or amount they do not recognize or believe is incorrect.

4. **If the customer identifies a problematic charge.**
   - Restate the selected transaction's purchase date, merchant, and amount and ask for correction if more than one record could match.
   - The available dispute guidance permits a credit-card transaction dispute for unauthorized charges, duplicates, incorrect amounts, goods/services not received, items not as described, continued charges after cancellation, or a promised refund that did not appear. Merchant contact is recommended first when appropriate, but suspected fraud can be raised promptly.
   - A dispute is initiated through customer service using the purchase date, merchant, and amount. There is no dispute-creation tool in this runtime. Do not claim that a dispute was filed, a refund was issued, a card was blocked, or a charge was removed. Follow the execution environment's normal customer-service escalation process if an action beyond review is required.

## Formatter helper

`scripts/format_card_transactions.py` accepts JSON on stdin and emits JSON on stdout. It has no external dependencies.

**Input schema**

```json
{
  "target_card_type": "<exact selected card type>",
  "raw_transaction_result": "<full result text from get_credit_card_transactions_by_user>",
  "limit": 10
}
```

Alternatively, provide `transactions` as an array of objects returned by another structured runtime instead of `raw_transaction_result`. Each transaction needs `credit_card_type` and `transaction_date`; other displayed fields are preserved when present. `limit` is optional and, when omitted, all matching records are returned.

**Output schema**

```json
{
  "ok": true,
  "target_card_type": "...",
  "matched_count": 0,
  "shown_count": 0,
  "transactions": []
}
```

Records in `transactions` are sorted newest first and contain only parsed transaction fields. On invalid input, the script emits `{"ok": false, "error": "..."}`. A runnable invocation is `python3 scripts/format_card_transactions.py`, with one input-schema JSON object supplied on standard input.

Before responding, verify that every listed item has the selected card type, a merchant, date, and amount as returned by the transaction lookup, and that no conclusion about fraud or duplication was presented as fact.
