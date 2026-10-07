---
name: recent-credit-card-transactions
description: Retrieve, filter, total, and clearly present a customer's recent transactions for a specifically named credit card. Use when a customer asks to review charges over a stated date range, especially to investigate a higher-than-expected balance.
---

# Recent Credit Card Transactions

Use this Skill to give a precise, read-only transaction review. It does not determine whether a charge is fraudulent, change an account, or file a dispute.

## Required information

1. Identify the customer using the identifier they provide (user ID, exact full name, or email) and use the appropriate user lookup tool if needed.
2. Confirm the requested card type and the date range. If either is ambiguous, ask a focused clarification rather than guessing.
3. Obtain the current time with `get_current_time`, the customer's card accounts with `get_credit_card_accounts_by_user`, and their transaction history with `get_credit_card_transactions_by_user`.
4. Select only records whose card type exactly matches the requested card. For a request for the “last N days,” use the current date minus N calendar days as the inclusive cutoff when transactions provide dates but not times. State the resulting inclusive date range in the reply.

Do not mix transactions from another card simply because they belong to the same customer. Do not claim that the sum of displayed purchases equals the current balance: payments, credits, prior purchases, interest, fees, and pending activity may affect a balance and may not be present in the returned history.

## Optional deterministic filtering helper

Run `scripts/filter_transactions.py` with JSON on stdin after copying the actual tool results into its input. It accepts either structured record arrays or the text returned by the account/transaction tools.

Input schema:

```json
{
  "as_of": "current timestamp returned by get_current_time",
  "card_type": "requested card type",
  "days": 30,
  "transactions": [
    {
      "transaction_id": "...",
      "credit_card_type": "...",
      "merchant_name": "...",
      "transaction_amount": "$0.00",
      "transaction_date": "MM/DD/YYYY",
      "category": "...",
      "status": "..."
    }
  ],
  "accounts": [
    {"card_type": "...", "current_balance": "$0.00"}
  ]
}
```

`transactions` and `accounts` may instead be the corresponding raw text tool result. The script emits JSON with `ok`, the calculated inclusive date window, matching transactions in chronological order, a cents-safe total, an optional reported account balance, and any nonfatal warnings. It emits `ok: false` with an error when required inputs are missing or no usable date can be parsed. Do not treat a failed helper run as a reason to invent results; recheck the tool output or clarify the date range.

Example invocation (with runtime-derived, not hardcoded, values):

```sh
python3 scripts/filter_transactions.py <<'JSON'
{"as_of":"<tool timestamp>","card_type":"<requested card>","days":30,"transactions":<actual transaction records>,"accounts":<actual account records>}
JSON
```

## Customer response

Give a compact, scannable answer containing:

- the named card and the inclusive date window used;
- every matching charge, with date, merchant, amount, category, and status (and transaction ID if helpful for follow-up);
- the total of the displayed transaction amounts;
- the reported current balance for that same card, if it was returned, labeled as a current balance rather than as the transaction total.

Use currency formatting to two decimals. Explain that the listed total is the total of the returned transactions in the selected window, not necessarily the amount currently owed. Do not expose unrelated account balances or unnecessary profile data. If no matching records exist, say so plainly and include the window searched.

If the customer identifies a particular charge as unauthorized or asks to dispute it, do not label it resolved. Follow the available dispute/fraud procedure or, if no suitable supported tool/process is available, transfer using the applicable supported transfer reason.

## Identity-verification audit

The normal verification tool documents a verification record requirement after a customer has successfully confirmed two of the four identity fields (date of birth, email, phone number, address). When that verification has actually occurred, obtain the current time and call `log_verification` with the stored complete fields and timestamp. Do not count an unconfirmed lookup result as confirmation, do not ask the customer to repeat sensitive values unnecessarily, and do not log a verification that did not occur.
