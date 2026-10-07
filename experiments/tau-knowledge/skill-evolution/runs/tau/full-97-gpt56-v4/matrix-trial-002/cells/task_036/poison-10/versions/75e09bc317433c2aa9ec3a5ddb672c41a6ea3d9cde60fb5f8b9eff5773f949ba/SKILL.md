---
name: credit-card-recent-activity-review
description: Safely verifies a customer and reviews recent posted credit-card transactions for a specified card when the customer questions their statement balance or asks to see recent charges.
---

# Credit Card Recent Activity Review

Use this Skill for a read-only request to view, explain, or reconcile recent credit-card activity. It supports a request for a named card and either a stated date range/count or a vague request such as “recent” or “last several.” It does not open a dispute, change an account, or make a payment.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required controls

1. Treat viewing transaction history as a banking action. Do not disclose card activity until identity is verified.
2. Obtain and independently compare **two of four** identity fields: date of birth, email, phone number, and address. An email used to locate the account may count as one field only if the customer supplied it and it matches the retrieved record.
3. Retrieve the customer record with the appropriate user lookup tool, compare the two supplied fields to that record, obtain the current timestamp with `get_current_time`, then call `log_verification` with all fields returned in the customer record and that timestamp.
4. Verify authority and ownership by retrieving the customer’s credit-card accounts and confirming that the requested card type belongs to that verified user. Confirm the requested card name with the customer if it is ambiguous or absent.
5. For this read-only review, product eligibility, available credit, fees, limits, cutoffs, recipient details, and transaction confirmation are not applicable. Do not invent values for them. Card details and ownership remain applicable. If the request becomes a payment, transfer, card change, dispute, block, or other action, stop and follow that action’s applicable prerequisites before proceeding.
6. Retrieve the verified customer’s transaction history, filter to the verified card type, and clearly retain each transaction’s date, merchant descriptor, amount, category (when available), and status. Never blend activity from another card.

## Workflow

1. Identify the requested card and requested coverage. If no count or date range is supplied, state that you will show the five most recent transactions by transaction date; this is the default interpretation of “last several.” Ask a clarifying question instead if a five-item default would not answer the request.
2. Complete the verification and ownership controls above. If a second identity field is missing, ask only for a second field; do not disclose transactions while waiting.
3. Call `get_credit_card_transactions_by_user` using the verified user ID. If card balance context is helpful, use the previously retrieved owned-card record; do not imply that the listed transaction total equals the statement balance unless the statement cycle, payments, credits, pending items, and prior balance are known.
4. Prepare the list with `scripts/recent_activity.py` or apply its documented ordering rules manually. Supply only transaction data retrieved during the current interaction.
5. Respond with the requested card name and a newest-first list. For each item, include date, merchant, amount, category if present, and status. Mention the current card balance only when it came from the verified owned-card record, and label it as the current balance.
6. If the customer recognizes none or some charges as unfamiliar, first invite them to identify the specific dated merchant entries and explain that posted date and merchant descriptor should be reviewed before starting a separate dispute workflow. Do not open a dispute without its required process and confirmations.

## Formatter script

`scripts/recent_activity.py` is a deterministic formatter and selector. It performs no banking calls and does not verify identity; use it only after the controls above are complete.

Run it by passing JSON on standard input, for example:

```json
{
  "card_type": "requested card type",
  "limit": 5,
  "transactions": [
    {
      "credit_card_type": "requested card type",
      "transaction_date": "MM/DD/YYYY",
      "merchant_name": "merchant descriptor",
      "transaction_amount": "$12.34",
      "category": "category",
      "status": "COMPLETED",
      "transaction_id": "optional record identifier"
    }
  ]
}
```

The script writes one JSON object. On success it includes `ok: true`, the selected `transactions` in descending date order, and `display_lines` that can be used in the customer response. `limit` defaults to 5 and must be an integer from 1 through 20. It matches the requested card type case-insensitively after trimming whitespace. It accepts `MM/DD/YYYY` or ISO `YYYY-MM-DD` dates. Missing required transaction fields, invalid dates, an invalid limit, or no matching transactions returns `ok: false` with an `error` and must be handled without fabricating results.

## Validation before responding

- Verification was logged only after two matching customer-provided identity fields were confirmed.
- The named card is in the verified user’s account list.
- Every displayed transaction matches that card and is ordered newest first.
- Each displayed amount, date, merchant, and status matches the retrieved record.
- The response does not reveal other account/card activity or claim a diagnosis of the balance discrepancy without enough statement-cycle information.
