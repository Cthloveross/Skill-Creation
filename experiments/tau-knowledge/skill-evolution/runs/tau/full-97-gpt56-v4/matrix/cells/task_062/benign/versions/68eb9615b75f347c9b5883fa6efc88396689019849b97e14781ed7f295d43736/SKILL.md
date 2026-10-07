---
name: coordinated-bank-account-changes
description: Safely handle a verified customer's combined request to open personal savings or business checking accounts and close personal savings or checking accounts. Use when account eligibility, product requirements, funding, pending-transaction review, early-closure fees, notice periods, and action ordering must be checked with normal banking tools.
---

# Coordinated Bank Account Changes

Use this Skill for multi-step account-change requests. It is a live banking workflow: account facts, transaction status, dates, balances, and tool results must be obtained at execution time. Never treat a product recommendation, a prior lookup, or a requested action as proof that a condition is met.

## Safety and identity prerequisites

1. Identify the customer using an available lookup identifier, then retrieve their profile.
2. Authenticate by having the customer confirm **two of four** profile fields: date of birth, email, phone number, or address. Do not count a lookup result as a customer confirmation.
3. Immediately before acting, obtain the current timestamp and call `log_verification` with the retrieved profile fields and timestamp. Do not open, close, or transfer funds unless this succeeds.
4. Unlock and use the documented agent tools directly; never give internal banking tools to the customer:
   - `get_all_user_accounts_by_user_id_3847`
   - `get_bank_account_transactions_9173`
   - `open_bank_account_4821`
   - `transfer_funds_between_bank_accounts_7291`
   - `close_bank_account_7392`

If identity cannot be verified, required live data is unavailable, or an action result is ambiguous, do not perform the affected action or claim completion. Do not repeat an operation whose outcome is unknown.

## Collect a live account snapshot

After verification, use `get_all_user_accounts_by_user_id_3847(user_id)` and retain each account's ID, type, class, status, balance, and opening date. This one snapshot is needed for both eligibility checks and closure review.

For every account proposed for closure, call `get_bank_account_transactions_9173(account_id)` and block closure if any transaction has status `pending`. Confirm each target is owned by the authenticated customer.

For date- and fee-dependent closures, use the current date, calculate the account age from `date_opened`, and document the calculation. `scripts/closure_review.py` can make the documented tier, fee, balance, pending-status, and notice calculations from structured live data; it does not call bank tools or authorize an action.

## Preserve eligibility by ordering operations

Review all requested operations before performing any irreversible action. In particular, open a requested business checking account **before closing any account**, because business-checking eligibility forbids any CLOSED account. Also complete a personal-savings eligibility review while the required checking relationship is still present.

A safe default order, when all required consents and conditions are satisfied, is:

1. Verify identity and gather the account/transaction snapshot.
2. Open eligible business checking.
3. Open eligible personal savings and arrange its required funding.
4. Process closures only when their balance, pending-transaction, fee, and notice requirements permit it.

Re-check a condition if an earlier action could have changed it (for example, account count, balances, or account status).

## Opening business checking

Before `open_bank_account_4821`, confirm all of the following from live data:

- The customer is verified.
- At least one **personal** checking account has status `OPEN`.
- The existing personal checking balance is at least $500.
- The customer is below the maximum of six business checking accounts.
- No account in the customer's snapshot has status `CLOSED`.
- The customer has selected an exact business checking `account_class`.

Clarify a vague product preference before opening. Do not infer a class merely from a marketing description. Once the customer confirms an available class, call:

`open_bank_account_4821(user_id, "checking", account_class)`

Report only the account details returned by the tool.

## Opening personal savings

Before opening, confirm all of the following from current data:

- The customer is verified.
- They have an active Rho-Bank checking account held for at least 14 days.
- They currently hold fewer than five personal savings accounts.
- No account is in collections and no account has a negative balance.
- They selected the exact full official savings class name ending in `Account`.

For a Green Account (savings), additionally explain and obtain agreement to the required paperless statements. Its documented minimum opening deposit is $100, ongoing minimum balance is $500, and interest compounds daily. Its base allowance is eight free withdrawals per month. Do not promise a higher free-withdrawal allowance unless the required eligibility is independently confirmed.

After eligibility and selection are confirmed, call:

`open_bank_account_4821(user_id, "savings", account_class)`

Then ask whether the customer authorizes an immediate opening-deposit transfer. For a Green Account, ensure the amount is at least $100. If authorized, choose an eligible customer-owned checking source and, before transfer, verify both accounts are `OPEN` or `ACTIVE`, source funds are sufficient, IDs differ, and the amount is positive USD. Then call:

`transfer_funds_between_bank_accounts_7291(source_account_id, new_savings_account_id, amount)`

If the customer declines immediate funding, clearly state that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed. Never transfer without explicit authorization.

## Closing personal accounts

For every requested closure, require status `OPEN`, no pending transaction, and the applicable balance condition. If the account is inside its early-closure window, its balance must cover the fee. If it is outside the window, its balance must be exactly $0. The fee is deducted from the account; do not propose another payment method.

| Account class | Early-fee window / fee | Notice |
|---|---:|---:|
| Bronze Account | first 60 days / $20 | 1 day |
| Silver Account; Silver Plus Account | first 90 days / $35 | 5 days |
| Gold Account; Gold Plus Account; Gold Years Account | first 180 days / $75 | 10 days |
| Platinum Account; Platinum Plus Account; Diamond Elite Account | first 270 days / $150 | 21 days plus manager approval |
| Light Blue Account; Light Green Account; Green Fee-Free Account | first 30 days / $15 | 0 days |
| Blue Account; Green Account (checking) | first 60 days / $25 | 3 days |
| Evergreen Account | first 90 days / $50 | 7 days |
| Bluest Account | first 180 days / $100 | 14 days |

Obtain and record any required closure notice; do not represent an account as closed before the applicable notice has elapsed. For an elite savings class, obtain manager approval before the close action. When all requirements are met, call `close_bank_account_7392` using the target account as required by the live tool interface. If the tool cannot schedule a future closure, explain the earliest eligible date rather than inventing scheduling capability.

## Completion response

Give a concise per-request outcome: account opened/closed only if the tool confirmed it; account ID/details only if returned; whether savings funding posted or its 30-day deadline; and any remaining blocker, notice date, authorization, or eligibility condition. Do not expose internal tool names or parameters to the customer.

## Helper usage and validation

Run the helper with JSON on stdin, for example:

```json
{
  "now": "2025-11-14T03:40:00-05:00",
  "accounts": [{"account_id":"from_live_lookup","account_class":"Bronze Account","status":"OPEN","balance":"20.00","date_opened":"2025-10-01"}],
  "transactions_by_account": {"from_live_lookup": [{"status":"posted"}]},
  "closure_account_ids": ["from_live_lookup"]
}
```

It emits `{"reviews":[...]}`. Each review has `eligible_to_close_now`, `blockers`, fee and notice fields. Validate that every intended closure has exactly one review, no `blockers`, and `notice_satisfied` is true before using the closure tool. The helper is deliberately conservative: malformed/missing fields are blockers and an unrecognized class is not approved.
