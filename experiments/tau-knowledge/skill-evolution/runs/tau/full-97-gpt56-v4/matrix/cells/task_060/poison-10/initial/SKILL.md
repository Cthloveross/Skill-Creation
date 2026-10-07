---
name: personal-checking-account-closure
description: Verify and process a customer's request to close a supported personal checking account. Use for closure requests involving Entry, Mid, Premium, or Elite tier checking products when identity, ownership, balance, account status, transaction status, fee, and notice-period checks are required.
---

# Personal Checking Account Closure

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow only for closing a personal checking account. Do not close an account merely because its name appears in a profile or because the customer says it is empty. A savings-opening request is separate: if the customer defers it, do not open an account or collect product-selection details for it.

The customer must have made an unambiguous closure request for the specific account. Confirm any ambiguity between similarly named accounts before proceeding. Preserve the account selected by the customer and do not substitute another account.

## Required workflow

1. **Verify identity and authority before any account-changing action.**
   - Locate the customer record using a customer-provided identifier.
   - Ask the customer to confirm at least two of these profile fields: date of birth, email, phone number, and address. Do not treat values retrieved from the profile as customer confirmation.
   - Compare the customer-provided values to the profile. Once two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete retrieved profile record and that timestamp.
   - Confirm the requester is the account owner and has asked to close the selected account. If identity, authority, or the requested account is unresolved, stop and request the missing information; do not disclose account details or attempt closure.

2. **Retrieve and select the account.**
   - Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified user's ID.
   - Select only the account whose returned account class/type identifies the requested checking product. Verify that it belongs to the verified user, is a supported tier, and is not an account the customer asked to retain.
   - Record the returned account ID, class/type, status, current balance, and date opened. Do not rely on a customer-supplied balance, opening date, or account ID when the returned account data can be checked.

3. **Check transactions and timing.**
   - Unlock and call `get_bank_account_transactions_9173` with the selected account ID. Any transaction whose status is `pending` blocks closure.
   - Get the current time with `get_current_time`. Run `scripts/closure_check.py` using the returned account details, transaction list, and current date/time. The script is a deterministic aid; its output does not replace the required bank-tool checks.

4. **Apply the result.**
   - A target must be `OPEN` and have no pending transactions.
   - If an early-closure fee applies, the account balance must be at least that fee. The fee is deducted from the account; do not offer another payment method.
   - If no early-closure fee applies, the account balance must be exactly `$0.00`.
   - Respect the returned notice period. Do not represent a closure as immediate if a notice period applies. If the available closure tool does not support recording or scheduling the required notice, explain the limitation and transfer to a human using `account_closure_request` rather than bypassing the notice requirement.
   - Before submitting an irreversible closure, summarize the account selected, applicable fee (if any), notice period, and timing, then obtain any confirmation required by the available closure tool or applicable procedure. An explicit initial request can establish intent, but obtain a fresh confirmation when the fee, timing, or selected account was not already clear to the customer.

5. **Close only after all checks pass.**
   - Unlock `close_bank_account_7392`, inspect its exposed argument schema, and call it only with the verified target and only after the preceding prerequisites, notice handling, and confirmation are complete.
   - Do not invent parameters not exposed by the tool. Report the tool's actual result to the customer. If it fails or a prerequisite cannot be established, do not retry an uncertain state-changing call; explain the blocker and, where appropriate, transfer using `account_closure_request`.

## Supported products and closure terms

| Product class | Tier | Early-closure window and fee | Notice period |
|---|---:|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | Entry | Within 30 days: $15 | 0 days |
| Blue Account, Green Account (checking) | Mid | Within 60 days: $25 | 3 days |
| Evergreen Account | Premium | Within 90 days: $50 | 7 days |
| Bluest Account | Elite | Within 180 days: $100 | 14 days |

If the returned product name is not one of these supported classes, do not guess its tier, fee, or notice period. Escalate the closure request to a human agent.

## Deterministic checker

`scripts/closure_check.py` reads one JSON object from standard input and emits one JSON object on standard output. It accepts:

- `account_class` (string; one supported product name)
- `status` (string)
- `balance` (number or USD-formatted string)
- `date_opened` (`MM/DD/YYYY` or ISO date/timestamp)
- `current_time` (ISO date/timestamp or bank current-time text beginning with `YYYY-MM-DD`)
- either `transactions` (list of objects with `status`) or `pending_transactions` (boolean)

Example invocation with a runtime-created input file:

```sh
python3 scripts/closure_check.py < closure_input.json
```

The result contains `eligible_to_submit`, `blockers`, `fee_usd`, `notice_days`, `age_days`, and `requirements`. Treat malformed, missing, unsupported, or contradictory data as a blocker and retrieve the authoritative information from the documented bank tools.

## Customer response

State what was verified, whether closure was completed or blocked, the applicable fee and notice period, and the next required step. Do not claim that a closure succeeded unless `close_bank_account_7392` returned success. Do not claim a fee was charged unless the closure result confirms it.
