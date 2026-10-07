---
name: verified-credit-card-transaction-review
description: Verify a cardholder with two identity fields, log that verification, then retrieve and present only the requested credit-card's transactions and balance. Use for card statement/balance reviews, unfamiliar transactions, and an explicit stolen-card or unauthorized-charge escalation.
---

# Verified credit-card transaction review

Use this Skill to answer a customer's request to see recent charges on a named card. It is a read-only review until an explicit fraud/security report is escalated. Never expose account data based on a name alone.

## 1. Identify and verify before disclosure

1. Obtain an exact full name, user ID, or email and use the matching user lookup tool. A name lookup is only for locating a record; it is not authentication.
2. Ask the customer to provide **two** of these four values: date of birth, email address, phone number, or address. Do not reveal stored values or turn a stored value into a prompt.
3. Compare the provided values against the located user record. If two values match, call `get_current_time` and then `log_verification` with the complete returned record and that timestamp. Do this before revealing card names, balances, or transactions.
4. If fewer than two values match, do not log verification or disclose account information. Ask for two values again.

The optional `scripts/verify_identity.py` checker takes the located record plus customer claims as JSON and returns only whether at least two claims match. It does not replace the required `log_verification` tool call.

## 2. Retrieve the requested activity

After successful verification:

1. Call `get_credit_card_accounts_by_user` and select the card whose `card_type` exactly equals the requested card. If none matches, say so; if the request is ambiguous, ask the customer to choose rather than selecting a similar card.
2. Call `get_credit_card_transactions_by_user`.
3. Keep only transactions whose `credit_card_type` exactly equals the selected `card_type`. Do not combine records from other cards.
4. Sort those records newest first by returned transaction date. Do not call a transaction pending unless its returned status says so.

## 3. Give a precise read-only report

State the selected card and returned current balance, if present. For each shown matching record, provide its date, merchant descriptor, amount, category, and status. Say how many matching records are shown; if the list is truncated, also state the total matched count and offer filtering by date, merchant, or amount. Do not call the result a complete statement reconciliation.

For a balance concern, say only that the returned transaction list does not by itself establish the cause of the balance. Do not infer or invent additional activity, payments, credits, fees, interest, or another cause.

If the customer says a charge looks unfamiliar, first restate the returned date, merchant descriptor, amount, and status so it can be reviewed. Do not say the charge is fraud merely because it is unfamiliar.

Use `scripts/format_transactions.py` to avoid counting, filtering, or ordering mistakes when structured tool records are available. It reads this JSON from stdin and writes JSON to stdout:

```json
{"card_type":"exact requested type","accounts":[...],"transactions":[...],"max_items":25}
```

Its output includes `matched_count`, `shown_count`, `truncated`, the filtered sorted `transactions`, and `markdown`. Before sending, check that the number stated equals the displayed records and that every row belongs to the selected card.

## 4. Explicit unauthorized-charge or card-security report

When the customer explicitly says a returned charge is unauthorized, says card information was stolen, or requests card-security action:

1. Acknowledge the concern without asserting fraud has been confirmed.
2. Do not file a dispute, cancel the card, replace it, or make another account change: no declared banking tool in this Skill supports those actions.
3. Call `transfer_to_human_agents` with `reason: "fraud_or_security_concern"`. Include only returned facts in the summary: selected card, each reported date/merchant/amount, the customer's report, requested cancellation/replacement if any, verification status, and that no account changes were made.
4. After a successful transfer, tell the customer a human agent will assist shortly. Do not make a duplicate transfer. If they repeat a cancellation/replacement request, explain that this chat cannot perform it and that the already-escalated agent will address the request.

