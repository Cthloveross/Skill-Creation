---
name: review-credit-card-transactions
description: Securely identify a banking customer and provide a clear, read-only review of recent transactions for the specific credit card they name. Use when a customer says their credit-card balance or statement looks wrong and asks what has been charged.
---

# Review Credit-Card Transactions

Use this skill for a read-only transaction inquiry. Do not change account data, initiate a dispute, block a card, or make any transfer merely because the customer reports an unexpected balance.

## Required controls

Before disclosing account, card, balance, or transaction information, verify the customer's identity and authority. Obtain confirmation of at least two of these four identity fields: date of birth, email address, phone number, and address. A name, user ID, or email can be used to locate a potential record but is not itself sufficient verification.

After two fields match the record:

1. Call `get_current_time`.
2. Call `log_verification` with the complete retrieved customer record and that timestamp.
3. Only then disclose the requested card and transaction information.

If the customer cannot complete verification, explain that account details cannot be disclosed until verification is complete. Do not reveal which field failed or disclose any account details. If lookup returns no record or more than one plausible customer and the ambiguity cannot be resolved without disclosure, ask for a different identifying value or offer the appropriate human transfer.

## Procedure

1. Identify the requested card product precisely. If the customer has not named a specific card, ask which card they mean; never choose based on balance or recency.
2. Locate the customer with the supplied name, email, or user ID using the matching user lookup tool.
3. Complete the required two-field identity verification and create the verification log as above.
4. Call `get_credit_card_accounts_by_user` and confirm that the exact requested card type belongs to the verified customer. If it does not, state that no matching card was found; do not expose other-card details.
5. Call `get_credit_card_transactions_by_user` for the verified customer.
6. Filter results by exact equality of `credit_card_type` to the requested card type. Never include transactions from the customer's other cards.
7. Sort by `transaction_date` descending. Treat the tool's status as authoritative and preserve it; do not imply that a completed transaction is pending, fraudulent, reversed, or a hold without evidence.
8. Present a useful recent-activity review. Unless the customer specifies a date range or count, show the most recent transactions that fit comfortably in the response and say that the list is the recent activity available from the lookup. For each transaction include date, merchant, amount, category when present, and status. Include the card's current balance only after verification and only when it helps answer the balance question.
9. Ask whether any listed charge is unfamiliar or whether the customer wants a narrower date range. If they report an unfamiliar transaction, gather the transaction details and follow the applicable dispute/fraud workflow; do not assert fraud based solely on their concern.

## Explaining a higher-than-expected balance

Keep explanations conditional and grounded in available records. A merchant authorization hold can temporarily reduce available credit and may not appear immediately in recent transactions; hotels, rentals, and fuel purchases commonly use them. A finalized hold becomes a posted charge, and release timing depends on merchant settlement practices. Do not claim a hold exists unless a tool result or the customer provides evidence. If the visible posted activity does not explain the concern, invite the customer to identify the questionable merchant, amount, and date for further review.

## Tool and output checks

- Customer lookup: `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id` requires the corresponding identifier.
- Card lookup and transaction lookup both require the verified `user_id`.
- Verification logging requires all customer-record fields plus the timestamp returned by `get_current_time`.
- Confirm the requested card appears in the account result before using the transaction result.
- Validate before responding that every displayed transaction has the requested exact card type, belongs to the verified user, and contains a date, merchant, amount, and status.
- If a tool fails or returns incomplete data, say what cannot be confirmed and do not manufacture transactions, balances, dates, or statuses.

## Example response structure

After successful verification and lookup, respond in concise customer-facing prose:

```
I found your [card type]. Its current balance is [balance]. Here is the recent activity I found:

- [date] — [merchant] — [amount] ([category], [status])
...

Do you recognize these charges, or would you like me to focus on a particular date or merchant?
```

This is a read-only review; do not treat the response itself as authorization for any banking action.