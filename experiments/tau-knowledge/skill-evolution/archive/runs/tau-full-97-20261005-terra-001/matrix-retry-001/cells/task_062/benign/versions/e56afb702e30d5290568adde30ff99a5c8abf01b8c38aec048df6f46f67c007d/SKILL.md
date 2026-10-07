---
name: coordinated-bank-account-overhaul
description: Safely coordinate a verified customer's linked requests to close personal Bronze savings and Evergreen checking accounts, open a business checking account, and open a personal savings account. Use when multiple account-opening/closure prerequisites, account dependencies, funding, debit cards, and business documentation must be checked before banking actions.
---

# Coordinated Bank Account Overhaul

Use this Skill to plan and execute a multi-step account change without closing an account that is still needed for eligibility. It is designed for an execution agent with the normal Rho-Bank tools named in the procedure below.

## Core safety rules

- Treat a profile lookup as identification only, **not** as identity verification. Verify two of the four identity fields (date of birth, email, phone, address), obtain the current time, then call `log_verification` before any account opening, closure, or transfer.
- Do not call an action tool until its workstream's prerequisites are confirmed from live records. Missing fields are blockers, not evidence that a requirement passed.
- Do not expose internal tools or ask the customer to call them.
- Preserve at least one qualifying personal checking account until all operations that depend on one are completed. A business checking account does not substitute for the personal checking prerequisite.
- Obtain the customer's explicit confirmation of each account class and explicit authorization for every transfer. Do not infer an opening-deposit amount.

## Runtime data collection

1. Identify the customer with `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id`.
2. Verify two identity fields and record verification using `log_verification` with all returned profile fields and a timestamp from `get_current_time`.
3. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Retain account ID, type, class, status, balance, and date opened for every account.
4. For each requested closure candidate, unlock and call `get_bank_account_transactions_9173(account_id)` to identify pending transactions.
5. For every checking account that may be closed, unlock and call `get_debit_cards_by_account_id_7823(account_id)`. All associated cards must be closed before closing that checking account. If a card must be closed, follow the debit-card closure requirements before using `close_debit_card_4721`: verified owner, ACTIVE or PENDING status, no pending transactions, no pending refunds (or written acknowledgment that the refund credits the linked checking account), and at least 14 days since issue unless the reason is lost, stolen, or suspected fraud.

The supplied `scripts/plan_overhaul.py` can turn normalized collected records into a transparent blocker report. It does not call banking tools or make banking changes.

## Dependency-aware execution order

The customer's requested order is important, but must not override eligibility or mandatory notice periods.

1. **Validate all requested accounts and initiate the Bronze closure workstream.** For Bronze savings, require OPEN status, no pending transactions, and either:
   - within 60 days of opening: balance at least $20 for the early-closure fee and a one-day notice period; or
   - after 60 days: exactly $0 balance.
   Do not call `close_bank_account_7392` until the notice requirement, if applicable, is satisfied.

2. **Keep the personal checking account open while opening accounts.** A business checking opening requires a verified customer, an existing personal checking account with status OPEN, fewer than six business checking accounts, no account with status CLOSED, and at least $500 in the existing checking account. Check all conditions from the live lookup before calling `open_bank_account_4821(user_id, 'checking', account_class)`.

   For a customer who requires a permanently $0 monthly maintenance fee rather than a temporary free period or a waivable fee, explain the documented distinction. Navy Blue is documented with $0 monthly maintenance fee and no minimum balance requirement; standard ACH is documented as free, while specific services can still carry charges. It is therefore a reasonable option to present for confirmation, not an automatic selection and not a promise that every possible service is free. Do not recommend a temporary-free startup account if it conflicts with this stated requirement. Confirm the exact business account class before opening.

   Gather and review applicable business onboarding documentation before proceeding: formation/registration evidence, authorization or resolution, tax ID and business contact details, beneficial-ownership information, and identity evidence for authorized holders. For multiple business holders, ensure the governance documentation authorizes them and do not exceed four joint holders.

3. **Open personal savings before closing the final qualifying personal checking account.** Personal savings requires verified identity, at least one active Rho-Bank checking account held at least 14 days, fewer than five personal savings accounts, no collections activity, and no negative balance on any account. Confirm the savings class using its complete official name ending in `Account`, then call `open_bank_account_4821(user_id, 'savings', account_class)` only after all checks pass.

   A Green Account (savings) may be presented to a customer seeking yield who can maintain its documented $500 minimum balance: it has a documented 4.0% APY and $0 monthly maintenance fee. Confirm the customer actually wants it; do not treat a recommendation as selection.

4. **Arrange the personal-savings opening deposit.** Ask whether the customer authorizes an immediate transfer from a specified checking account. If yes, validate that both accounts belong to the customer, have distinct IDs, are OPEN or ACTIVE, the amount is positive USD, and the source has sufficient available funds. Then call `transfer_funds_between_bank_accounts_7291(source_account_id, new_savings_account_id, amount)`. If the customer defers funding, state that the account must be funded by internal transfer or external deposit within 30 days or it will close.

5. **Close Evergreen last.** For Evergreen checking, require OPEN status, no pending transactions, and all associated debit cards already closed. It has a $25 early-closure fee within 60 days and a three-day notice period. Within that window, the balance must be at least $25; after the window it must be $0. Confirm any necessary authorized transfer or other resolution of excess funds before closure. Only after all prerequisites and notice requirements are met, call `close_bank_account_7392`.

After each tool success, use returned identifiers/statuses rather than assumptions. Confirm the resulting account details, each closure outcome or remaining notice date, and the new savings funding status/deadline.

## Failure handling

- If a closure has pending transactions, wait for settlement; do not close the account.
- If a closure balance fails the applicable rule, do not close it. An authorized internal transfer may be considered only when the transfer tool's prerequisites are met.
- If the Bronze closure cannot complete promptly due to its notice period, do not falsely say it is closed. Continue only with independent workstreams that do not violate the customer's wishes or an eligibility dependency.
- If closing Bronze is necessary to reduce the customer below five savings accounts, complete that closure before opening the new savings account.
- If Evergreen is the only personal checking account, do not close it until the business and personal-savings openings are complete. Opening business checking does not satisfy personal-savings eligibility.
- If any business-opening condition, documentation requirement, savings condition, customer selection, funding authorization, debit-card requirement, or manager/notice requirement is unresolved, state the specific missing item and stop that affected action.

## Planner script

Run with JSON on stdin:

```json
{
  "now": "2025-01-01T12:00:00",
  "identity_verified": true,
  "accounts": [{"account_id":"...","account_type":"checking","account_class":"...","ownership":"personal","status":"OPEN","balance":600,"date_opened":"2024-01-01"}],
  "transactions_by_account": {"account-id":[{"status":"posted"}]},
  "debit_cards_by_account": {"checking-id":[{"card_id":"...","status":"CLOSED"}]},
  "targets": {"bronze_savings_account_id":"...","evergreen_checking_account_id":"..."},
  "business_account_class": "...",
  "savings_account_class": "...",
  "business_documents": {"required": false}
}
```

Execute `python3 scripts/plan_overhaul.py`. The script emits JSON with `business_opening`, `savings_opening`, `bronze_closure`, `evergreen_closure`, and `ordering_notes`. Each workstream contains `ready`, `blockers`, and policy-derived details. It validates only provided data; the executor must still perform the live tool lookups, customer confirmations, required notices, and action calls.
