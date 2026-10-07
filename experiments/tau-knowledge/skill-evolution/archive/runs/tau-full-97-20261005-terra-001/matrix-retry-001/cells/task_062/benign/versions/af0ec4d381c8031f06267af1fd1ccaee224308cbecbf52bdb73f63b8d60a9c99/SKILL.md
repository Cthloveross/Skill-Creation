---
name: coordinated-bank-account-overhaul
description: Safely coordinate a verified customer's linked requests to close personal Bronze savings and Evergreen checking accounts, open a business checking account, and open a personal savings account. Use when multiple account-opening and closure prerequisites, account dependencies, funding, debit cards, and business documentation must be checked before banking actions.
---

# Coordinated Bank Account Overhaul

Use this Skill to plan and execute a multi-step account change without closing an account that is still needed for eligibility. It is designed for an execution agent with the normal Rho-Bank tools named below.

## Core safety rules

- A profile lookup is identification only, **not** identity verification. Verify two of the four identity fields (date of birth, email, phone, address), obtain the current time, then call `log_verification` before an account opening, closure, or transfer.
- Do not call an action tool until that workstream's live-record prerequisites are confirmed. Missing data is a blocker, not evidence that a requirement passed.
- Do not expose internal tools or ask the customer to call them.
- Preserve at least one qualifying **personal** checking account until all dependent operations are complete. A business checking account does not substitute for a personal-checking prerequisite.
- Obtain the customer's explicit account-class confirmation and explicit authorization for each transfer, including its source, destination, and amount. Do not infer an opening-deposit amount or disposition of a positive closure balance.
- A positive balance must be resolved through an authorized disposition before closure. Do not silently forfeit a surplus or move it without authorization, even where an early-closure fee may be deducted from the account.

## Runtime data collection

1. Identify the customer with `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id`.
2. Verify two identity fields and record verification with `log_verification`, using all returned profile fields and a timestamp from `get_current_time`.
3. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Retain account ID, type, class, status, balance, and date opened for every account.
4. For each closure candidate, unlock and call `get_bank_account_transactions_9173(account_id)` to identify pending transactions.
5. For every checking account that may close, unlock and call `get_debit_cards_by_account_id_7823(account_id)`. All associated cards must be closed before checking-account closure. Before calling `close_debit_card_4721`, verify the owner, ACTIVE or PENDING card status, no pending card transactions, no pending refunds (unless the customer gives the required written acknowledgement), and at least 14 days since issue unless the closure reason is lost, stolen, or suspected fraud.

`scripts/plan_overhaul.py` converts normalized collected records into a transparent blocker report. It never calls banking tools or makes banking changes.

## Dependency-aware execution order

The requested order matters, but it cannot override eligibility, balance disposition, card, or notice requirements.

1. **Validate both requested closures.**
   - Bronze savings: require OPEN status, no pending transactions, and apply its $20 early-closure fee within 60 days plus its one-day notice period. After 60 days, the account must have a $0 balance. For any positive funds that will not be consumed by an applicable fee, obtain an explicit authorized disposition before closure.
   - Evergreen checking: require OPEN status, no pending transactions, all linked debit cards closed, and apply its $25 early-closure fee within 60 days plus its three-day notice period. After 60 days, the account must have a $0 balance. Obtain explicit authorized disposition of positive funds before closure.
   - Do not call `close_bank_account_7392` until all applicable notice, balance, transaction, and card requirements are satisfied.

2. **Keep a personal checking account open while dependent opening work is performed.** Business checking requires a verified customer, at least one existing personal checking account with status OPEN, fewer than six business checking accounts, no account with status CLOSED, and an existing checking-account balance of at least $500. Confirm these from the live account lookup before calling `open_bank_account_4821(user_id, 'checking', account_class)`.

   For a customer requiring a permanently $0 monthly maintenance fee rather than a temporary free period or a waivable fee, Navy Blue is a suitable option to present for confirmation: it has a permanently $0 monthly maintenance fee and no minimum balance requirement. Standard ACH is free, but particular services may still carry charges. Do not imply that every service is free, and do not recommend a temporary-free startup account where it conflicts with the customer's stated requirement.

   Before considering a Navy Blue opening, request and review all business onboarding items. Use this explicit customer-facing checklist so no required topic is omitted:

   > To review the LLC opening, please provide your **formation/registration** documents; an **authorization or resolution** naming people authorized to act; the LLC **tax ID** and business contact details; **beneficial-ownership** information; and identity-verification materials for every account holder. If there will be multiple holders, please also provide governance evidence authorizing them; up to four joint business holders may be designated.

   Confirm the exact business account class before opening. Do not open it while any required onboarding evidence or business eligibility fact is missing.

3. **Open personal savings before closing the final qualifying personal checking account.** Personal savings requires verified identity; at least one active Rho-Bank checking account held at least 14 days; fewer than five personal savings accounts; no collections activity; and no negative balance on any account. Confirm the exact savings account class using the complete official name ending in `Account`, then call `open_bank_account_4821(user_id, 'savings', account_class)` only after every check passes.

   A Green Account (savings) may be presented to a customer who seeks yield and can maintain its documented $500 minimum balance: it has 4.0% APY and a $0 monthly maintenance fee. A recommendation is not a selection; obtain affirmative confirmation of the full official class name before opening.

4. **Arrange the personal-savings opening deposit.** Ask whether the customer authorizes an immediate transfer from a specified checking account. If yes, confirm both accounts belong to the customer, are distinct, are OPEN or ACTIVE, the amount is positive USD, and the source has sufficient funds. Then call `transfer_funds_between_bank_accounts_7291(source_account_id, new_savings_account_id, amount)`. If funding is deferred, state that an internal transfer or external deposit must fund the account within 30 days or it will close.

5. **Close Evergreen last.** Only after the business and personal-savings workstreams are complete or appropriately declined, all Evergreen cards are closed, positive funds have an authorized disposition, and all closure conditions and notice requirements are met, call `close_bank_account_7392`.

After every successful tool call, rely on returned identifiers and statuses rather than assumptions. Confirm completed account details, closure outcome or notice date, and savings funding status or deadline.

## Failure handling

- If a closure has pending transactions, wait for settlement; do not close it.
- If a closure has positive funds without an explicitly authorized destination or other documented disposition, request that authorization; do not transfer or close it.
- If a closure balance fails its applicable fee or zero-balance rule, do not close it.
- If Bronze closure cannot complete promptly due to its notice period, do not say it is closed. Continue only with independent workstreams that do not violate a dependency or customer instruction.
- If Bronze closure is necessary to reduce the customer below five personal savings accounts, complete the closure before opening the new savings account.
- If Evergreen is the only personal checking account, do not close it until the business and personal-savings openings are complete. Business checking does not meet the personal-checking condition for personal savings.
- If a business-opening condition, business document, savings condition, selection, funding authorization, debit-card requirement, or manager/notice requirement is unresolved, explain the specific missing item and stop that affected action.

## Planner script

Run `python3 scripts/plan_overhaul.py` with a JSON object on stdin. Example schema:

```json
{
  "now": "2025-01-01T12:00:00",
  "identity_verified": true,
  "accounts": [{"account_id":"...","account_type":"checking","account_class":"...","ownership":"personal","status":"OPEN","balance":600,"date_opened":"2024-01-01"}],
  "transactions_by_account": {"account-id":[{"status":"posted"}]},
  "debit_cards_by_account": {"checking-id":[{"card_id":"...","status":"CLOSED"}]},
  "targets": {"bronze_savings_account_id":"...","evergreen_checking_account_id":"..."},
  "business_account_class": "Navy Blue",
  "savings_account_class": "Green Account",
  "business_documents": {
    "formation_registration": true,
    "authorization_or_resolution": true,
    "tax_id": true,
    "business_contact_details": true,
    "beneficial_ownership": true,
    "holder_identity": true
  },
  "closure_balance_dispositions": {
    "bronze-account-id": {"authorized": true, "destination_account_id":"...", "amount":130},
    "evergreen-account-id": {"authorized": true, "destination_account_id":"...", "amount":3475}
  }
}
```

It emits JSON with `business_opening`, `savings_opening`, `bronze_closure`, `evergreen_closure`, and `ordering_notes`. `ready: true` is advisory only: the executor must still perform live lookups, obtain customer confirmations, satisfy notices, and invoke the correct banking tools.
