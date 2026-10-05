---
name: personal-bank-account-switch
version: 1.0.0
description: Safely handle a verified customer's request to open personal checking and/or savings accounts, fund a savings account, and close a prior checking account. Use for account-switch requests, including checking–savings APY pairing questions.
---

# Personal Bank Account Switch

Use this workflow when a customer wants to replace a checking account, open a personal savings account, arrange an opening deposit, or close the replaced checking account. Banking actions are performed only with the execution agent's normal banking tools.

## Mandatory controls

Before **every** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Establish the authenticated customer's `user_id` from a reliable profile lookup.
2. Verify identity by confirming two of the four profile fields (date of birth, email, phone number, address) with the customer. Retrieve the profile as needed, obtain the current timestamp, then call `log_verification` with all required profile fields and `time_verified`.
3. Confirm the customer is authorized to request each action. For a checking closure, obtain clear authorization to close the identified account; for an internal funding transfer, obtain the source account and exact amount authorization.
4. Do not infer account status, ownership, balances, account age, pending activity, debit-card status, or funding authorization from a customer's recollection. Retrieve and verify them.
5. Stop the affected action and explain the specific blocker if a prerequisite cannot be verified or is not satisfied. Do not substitute another product, source account, amount, or closure date without customer confirmation.

## Tool access and sequencing

The relevant internal tools are discoverable. Unlock a tool before calling it with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` using a JSON-string `arguments` payload.

Unlock only tools needed for the request:

- `get_all_user_accounts_by_user_id_3847(user_id)` — retrieve account IDs, types, classes, statuses, balances, and opening dates.
- `open_bank_account_4821(user_id, account_type, account_class)` — open an eligible personal account.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` — only for an authorized immediate savings opening deposit.
- `get_bank_account_transactions_9173(account_id)` — inspect account activity and identify pending account transactions before closure.
- `get_debit_cards_by_account_id_7823(account_id)` — identify cards attached to a checking account.
- `close_debit_card_4721(card_id, reason)` — close qualifying cards before the linked checking account is closed.
- `close_bank_account_7392(...)` — close an account only after all closure requirements are confirmed. Use the exact parameter schema supplied when the tool is unlocked.

After every write action, inspect the result. Do not claim an account was opened, funded, card closed, or account closed unless the tool confirms success. If a tool reports an error or an ambiguous result, do not retry blindly; explain the result and request the missing information or escalate according to normal procedures.

## Account opening workflow

### 1. Retrieve current account state

Call `get_all_user_accounts_by_user_id_3847` after identity verification. Use returned records—not assumptions—to count accounts, identify active checking accounts, determine checking tenure, find balances/statuses, and select the specific old account to close.

### 2. Eligibility checks

For **personal checking**, confirm all of the following:

- Customer is verified and authorized.
- Customer is at least 18.
- Customer currently has no more than four personal checking accounts; operationally, proceed only when the count permits one additional checking account.
- No checking account was closed for cause in the preceding six months.

For **personal savings**, confirm all of the following:

- Customer is verified and authorized.
- At least one active Rho-Bank checking account exists.
- Customer has fewer than five personal savings accounts.
- No account is in collections and no account has a negative balance.
- An active checking account has been held for at least 14 days.

If the requested savings account needs an opening deposit or paperless enrollment, confirm those requirements before representing the application as complete. For example, Green Account (savings) has a $100 minimum opening deposit and requires paperless statements.

### 3. Confirm exact selected products

Capture the account class exactly as selected by the customer. `account_class` must be the full official name ending in `Account`; never shorten, normalize, or guess it. Examples include `Evergreen Account`, `Green Account (savings)`, and `Silver Plus Account`.

When discussing a savings APY pairing, distinguish documented facts from an exhaustive market comparison. The documented pairing of `Evergreen Account` checking and `Green Account (savings)` qualifies for Evergreen's +0.55% linked-savings boost. Green savings has a 4.0% base APY, so this pairing is 4.55% before any separately applicable bonuses. Credit-card bonuses do not stack: only the highest applicable credit-card bonus applies. Multiple eligible checking boosts also do not stack: only the highest eligible checking boost applies. Do not call a pairing the absolute highest unless the available product documentation and the customer's complete eligible holdings support that conclusion.

### 4. Open accounts in a safe order

If both accounts are authorized, open the checking account first, then re-check that an active checking account exists and open the savings account. Call `open_bank_account_4821` with:

```json
{"user_id":"<authenticated user id>","account_type":"checking or savings","account_class":"<exact confirmed official name>"}
```

Use `checking` for personal checking and `savings` for personal savings. Record the newly returned account IDs and account details from successful results.

### 5. Handle savings funding

After opening savings, ask whether the customer authorizes an immediate opening-deposit transfer. If yes, verify the source is their active checking account, its available balance can cover the amount, the destination is the newly created savings account, and the amount satisfies the product's opening-deposit requirement. Then call the transfer tool with the confirmed IDs and amount.

If the customer declines or cannot authorize an immediate transfer, state that they have 30 days to fund the savings account through an internal transfer or external deposit or it will be closed. Do not transfer money merely because the customer mentioned an amount saved elsewhere.

## Checking-account closure workflow

Process closure independently from opening. A newly opened account does not make the prior account eligible for closure.

1. Identify the exact old checking account by its returned `account_id`, class, and customer confirmation.
2. Retrieve its transaction history. Its status must be `OPEN` and it must have no pending transactions.
3. Determine the tier and closure terms from the account class and opening date. For entry-tier `Light Blue Account`, `Light Green Account`, and `Green Fee-Free Account`, the early-closure fee is $15 when closure is within 30 days and there is no notice period. For closure with an applicable early fee, the balance must be at least the fee. If no early fee applies, the account balance/current holdings must be exactly $0. The fee is deducted from the account; do not use another payment method.
4. Retrieve all debit cards for that checking account. All associated cards must be closed before the account can close.
5. For each active or pending card to be closed, verify the card belongs to the customer, there are no pending/processing transactions, and there are no pending refunds (unless the customer provides the required written acknowledgement that the refund will credit to linked checking). Verify it has been active at least 14 days from `date_issued`, except lost, stolen, and suspected-fraud closures bypass that age requirement. Obtain a closure reason from: `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, `account_closing`. For a planned account closure, use the confirmed `account_closing` reason. Close each qualifying card and confirm its success.
6. Reconfirm all pre-closure conditions after card closures, including account balance, status, pending transactions, applicable fee, and customer authority. Only then invoke `close_bank_account_7392` with the unlocked tool's required parameters.

If an early fee applies and the old account has insufficient funds, do not close it. Explain the amount that must be present. If a card or account has pending activity, wait for it to settle. If the customer wants a card closed for loss, theft, or suspected fraud, follow the security-specific card workflow; pending transactions can still process.

## Completion response

Report separately: accounts successfully opened, account class, new account identifiers/details returned by the tool, funding status or deadline, cards closed, and whether the old checking account was closed. Include material product conditions: for Evergreen checking, the $6 monthly fee is waived with a $500 minimum daily balance; Green savings requires a $500 ongoing minimum balance but has no monthly maintenance fee. Do not promise an APY bonus that has not been verified as applicable.

## Optional eligibility helper

`scripts/evaluate_account_requirements.py` evaluates structured account facts into deterministic opening and checking-closure blockers. It is advisory only: it cannot verify identity, authority, pending card transactions/refunds, account-closure-for-cause history, or tool success. The execution agent must still perform every mandatory check above.

Input is a JSON object on stdin:

```json
{
  "operation":"checking_open|savings_open|checking_close",
  "today":"YYYY-MM-DD",
  "customer":{"verified":true,"age":30,"closed_checking_for_cause_within_6_months":false},
  "accounts":[{"account_id":"...","account_type":"checking","account_class":"...","status":"OPEN","balance":0,"date_opened":"YYYY-MM-DD","in_collections":false}],
  "target_account_id":"...",
  "pending_transaction_account_ids":["..."]
}
```

It emits JSON with `eligible`, `blockers`, `facts`, and `requirements_checked`. Invoke it through the packaged script runner only after supplying fresh tool-derived facts. A missing required datum is a blocker, not evidence of eligibility.
