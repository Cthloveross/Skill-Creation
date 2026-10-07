---
name: personal-checking-account-closure
version: 1.0.0
description: Verify and carry out an eligible personal checking-account closure, including mandatory linked-debit-card closure, account transaction checks, tier-based early-closure fees and notice periods. Use when a verified customer asks to close a personal checking account or replace it with a new checking account.
---

# Personal Checking Account Closure

Use this workflow for a customer-requested closure of a personal checking account. A replacement-account opening is a separate action: do not open one until the requested closure is complete and the customer has selected a specific account class and meets that product's opening requirements.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required information and tool access

The runtime may expose the banking operations as discoverable agent tools. Unlock each documented tool before calling it:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_debit_cards_by_account_id_7823(account_id)`
- `get_bank_account_transactions_9173(account_id)`
- `close_debit_card_4721(card_id, reason)`
- `close_bank_account_7392` (inspect its unlocked schema and supply only its documented required fields)

Use normal banking tools for all reads and actions. The packaged Python helper is a decision aid only; it never executes a banking action.

## Workflow

1. **Verify identity and authority before any banking action.**
   - Locate the customer record using customer-provided identifying information.
   - Ask the customer to confirm at least two of the four profile fields: date of birth, email, phone number, and address.
   - Retrieve the profile as necessary, compare the two confirmations, obtain the current timestamp with `get_current_time`, and call `log_verification` with the complete required profile fields and timestamp.
   - Treat a name alone, a prior lookup, or an unlogged assertion as insufficient verification. Do not retrieve accounts, cards, or transactions and do not close anything until verification is logged.
   - Confirm that the requestor is the owner of the selected account. Use the verified user ID for all customer-scoped lookups and confirm each card's `user_id` matches it.

2. **Identify the exact requested checking account.**
   - Retrieve all accounts for the verified user with `get_all_user_accounts_by_user_id_3847`.
   - Select only the account the customer requested. If multiple accounts could match the described type/class, ask the customer to identify the intended account; never close an arbitrary match.
   - Confirm it is a supported personal checking class, is `OPEN`, and its returned account record belongs to the verified customer.

3. **Determine the tier, early fee, and notice period.**

   | Tier | Supported account classes | Early-closure fee and window | Notice |
   |---|---|---|---:|
   | Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 when closed within 30 days of opening | 0 days |
   | Mid | Blue Account; Green Account (checking) | $25 when closed within 60 days of opening | 3 days |
   | Premium | Evergreen Account | $50 when closed within 90 days of opening | 7 days |
   | Elite | Bluest Account | $100 when closed within 180 days of opening | 14 days |

   Calculate account age from `date_opened` and the current date. For this helper and workflow, "within" includes the final calendar day of the stated window. If dates are missing or cannot be interpreted, do not guess whether a fee applies.

   - If an early fee applies, the current account balance must be at least the fee. The fee is deducted directly from that balance; no alternate payment method is permitted.
   - If no early fee applies, the current balance must be exactly $0.
   - For a nonzero notice period, do not submit the closure until the full notice period has elapsed from a recorded closure request. No notice-recording operation is documented here; if the runtime does not provide an authorized way to establish that record, explain the limitation and do not close prematurely.

4. **Check account transactions.**
   - Retrieve the selected account's transactions with `get_bank_account_transactions_9173`.
   - A transaction whose `status` is `pending` blocks closure. Posted transactions do not themselves block it.
   - Re-read account details and transactions immediately before the final account-close action, because balance, status, or transaction state can change.

5. **Close all linked debit cards before the account.**
   - Retrieve cards using `get_debit_cards_by_account_id_7823(account_id)`. Historical `CLOSED` cards require no action; every other linked card must be resolved before the account can close.
   - For each card to be closed, verify: matching `user_id`; current status is `ACTIVE` or `PENDING`; no pending or processing card transactions; no pending refunds; and at least 14 calendar days since `date_issued`.
   - The customer-requested reason for a card being closed because its account is closing is `account_closing`. This reason does **not** bypass the 14-day card-age rule. Only `lost`, `stolen`, and `fraud_suspected` bypass that rule, and they require the corresponding customer-reported reason.
   - If a pending refund exists, do not close the card unless the refund settles or the customer gives the documented written acknowledgement that it will be credited to the linked checking account. For an account that is also being closed, ensure the linked-account implications are resolved before proceeding.
   - The supplied procedures do not name a card-transaction or refund lookup tool. If the runtime cannot establish the pending-card-transaction and pending-refund checks through an authorized source, do not assume they are clear and do not call the card-close tool.
   - Once all checks pass, use `close_debit_card_4721` with `card_id` and `reason: "account_closing"`. Confirm the result, then re-query the account's cards and require every linked card to be `CLOSED` before proceeding.

6. **Close the checking account.**
   - Only after identity/ownership verification, card closure, account status, balance/fee, pending-transaction, and notice checks all pass, invoke `close_bank_account_7392` using the exact unlocked-tool schema.
   - Confirm the returned closure result. Explain any applicable fee and that a closed account/card cannot be reopened. For closed debit cards, advise that recurring card payments need new payment information and refunds to a closed card are credited to the linked checking account.

7. **Handle blockers accurately.**
   - Do not treat a customer's statement that money was moved out as proof of a zero balance.
   - State the specific unmet condition (for example, not yet verified, pending account transaction, insufficient fee balance, nonzero balance after the fee window, an open linked card, card under 14 days old, pending refund, or notice period not elapsed), and do not perform a closure action.
   - Do not infer unsupported account classes, fee rules, card/refund status, dates, or tool parameters.

## Decision helper

`scripts/evaluate_closure.py` accepts JSON on standard input and emits a JSON closure assessment on standard output. It accepts data already retrieved through authorized runtime tools; it does not read runtime systems or invoke banking operations.

Input schema:

```json
{
  "identity_verified": true,
  "verified_user_id": "string",
  "target_account_confirmed": true,
  "now": "YYYY-MM-DD or ISO-8601 timestamp",
  "account": {
    "account_id": "string",
    "user_id": "string",
    "account_type": "checking",
    "account_class": "Light Blue Account",
    "status": "OPEN",
    "balance": "0.00",
    "date_opened": "YYYY-MM-DD"
  },
  "transactions": [{"status": "posted"}],
  "cards": [{
    "card_id": "string",
    "user_id": "string",
    "status": "CLOSED",
    "date_issued": "YYYY-MM-DD"
  }],
  "card_checks": {
    "card-id": {"pending_transactions": false, "pending_refunds": false}
  }
}
```

`card_checks` is required for each non-closed card. Its values must come from authorized operational evidence, not an assumption. The output contains `account_close_eligible_now`, blockers, computed fee/notice information, and `card_close_candidates`. A candidate still requires the live checks and an actual close-card call; it is not a closure authorization.

Example invocation by an executor:

```sh
python3 scripts/evaluate_closure.py <<'JSON'
{"identity_verified":true,"verified_user_id":"user-id","target_account_confirmed":true,"now":"2025-01-01","account":{"account_id":"account-id","user_id":"user-id","account_type":"checking","account_class":"Light Blue Account","status":"OPEN","balance":"0.00","date_opened":"2024-01-01"},"transactions":[],"cards":[],"card_checks":{}}
JSON
```

Validate the output before using it: `supported_account_class` must be true; `input_errors` must be empty; every account blocker must be resolved; and `account_close_eligible_now` can be true only when `all_linked_cards_closed` is true. Re-query live data after any card closure and immediately before closing the account.
