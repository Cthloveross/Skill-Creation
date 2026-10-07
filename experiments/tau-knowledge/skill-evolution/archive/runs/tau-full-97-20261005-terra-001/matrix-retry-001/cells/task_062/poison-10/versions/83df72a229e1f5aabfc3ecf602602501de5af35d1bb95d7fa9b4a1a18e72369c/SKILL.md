---
name: banking-account-overhaul
description: Handle a verified customer's combined personal account-closure, business-checking opening, personal-savings opening, and internal-transfer requests. Use when each requested action requires independent eligibility, ownership, balance, pending-transaction, fee, notice, and authorization checks.
---

# Banking Account Overhaul

## Operating principles

Treat each requested opening, transfer, and closure as a separate banking action. A blocked closure or an incomplete savings request must **not** delay an independently eligible, customer-selected business-checking opening.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Use only accounts belonging to the verified customer. Do not ask the customer to invoke internal tools or expose internal tool parameters.

Do not claim an action succeeded until its banking tool returns success. Do not retry an unchanged failed action.

## Verify identity and retrieve the account record

1. Locate the customer profile using identifying information supplied by the requester.
2. Confirm two profile fields with the customer from date of birth, email, phone number, and address. A profile lookup alone is not verification.
3. Get the current time with `get_current_time` and record successful verification with `log_verification` using the authenticated profile fields and that timestamp.
4. Retrieve the customer's bank accounts with `get_all_user_accounts_by_user_id_3847(user_id)`.
5. Confirm each account used in a requested action belongs to the verified customer. Resolve any genuine ownership or authority conflict before acting.

## Required execution order for mixed requests

After identity verification and the account lookup:

1. Assess the selected business-checking request and, if eligible, **open it immediately in the same workflow turn**.
2. Review requested closures and identify blockers.
3. Assess personal-savings opening only if the customer supplied an exact official savings account class.
4. Perform an authorized balance disposition and then a closure only after every closure requirement is met.

Do not finish after saying that a selected business account is eligible. Once the documented checks pass, execute the opening before spending additional turns on blocked closures, a missing savings selection, recommendations, or optional product discussion.

## Business checking opening

A customer-selected business checking account may be opened only after confirming all of these requirements from the verified account record:

- The customer is verified.
- At least one existing **personal** checking account is `OPEN`.
- The customer has fewer than six business checking accounts.
- No customer account has status `CLOSED`.
- An existing qualifying personal checking account has a balance of at least $500.
- The customer selected a supported business-checking `account_class`.

Use account classification data returned by the account lookup to count personal and business accounts. If records provide a clear personal-checking classification, do not ask a redundant question. Ask for clarification only when classification is actually unavailable and is needed to determine eligibility.

After all checks pass, preserve the customer's exact selected class; do not substitute a promoted or recommended class. Unlock `open_bank_account_4821` and call it through the normal agent-tool interface with:

- `user_id`: verified customer's user ID
- `account_type`: `checking`
- `account_class`: exact selected business-checking class

For example, a verified and eligible selection of `Navy Blue` requires an immediate call using `account_type` `checking` and `account_class` `Navy Blue`. This is an agent action, not a suggestion for the customer to complete later.

If eligibility fails, state the specific unmet condition and do not open the account. If the opening tool succeeds, confirm the newly opened account. If it fails, report the failure without claiming completion.

## Closure review and execution

For every requested closure:

1. Identify the exact account by account ID and class in the verified account list. If multiple accounts match the requested description, ask the customer which account is intended.
2. Retrieve transaction history with `get_bank_account_transactions_9173(account_id)`. Any transaction whose `status` is `pending` blocks closure.
3. Confirm account status is `OPEN`, determine the opening date and current date, calculate the applicable early-closure fee and notice period, and obtain any required approval.
4. Confirm the required notice and customer confirmation are documented. For elite savings, obtain manager approval.
5. Unlock and call `close_bank_account_7392` only after every applicable condition passes.

A nonzero balance is never automatically transferable or disposable. Obtain explicit customer instructions before transferring a closure balance. If closure is blocked, keep the account open, explain the blocker, and request only the information or authorization necessary to resolve it.

### Personal savings closure terms

| Account class | Early-closure fee window | Notice | Additional requirement |
| --- | --- | ---: | --- |
| Bronze Account | Under 60 days: $20 | 1 day | — |
| Silver Account; Silver Plus Account | Under 90 days: $35 | 5 days | — |
| Gold Account; Gold Plus Account; Gold Years Account | Under 180 days: $75 | 10 days | — |
| Platinum Account; Platinum Plus Account; Diamond Elite Account | Under 270 days: $150 | 21 days | Manager approval |

### Personal checking closure terms

| Account class | Early-closure fee window | Notice |
| --- | --- | ---: |
| Light Blue Account; Light Green Account; Green Fee-Free Account | Under 30 days: $15 | 0 days |
| Blue Account; Green Account (checking) | Under 60 days: $25 | 3 days |
| Evergreen Account | Under 90 days: $50 | 7 days |
| Bluest Account | Under 180 days: $100 | 14 days |

If an early-closure fee applies, the account balance must be at least the fee because the fee is deducted directly from that account and there is no alternative payment method. If no early fee applies, the current balance must be exactly $0. A pending transaction, non-`OPEN` status, unsatisfied notice, or missing required approval also blocks closure.

## Personal savings opening

Do not infer a personal-savings selection from an abbreviation, an example, or a recommendation. Before opening personal savings, confirm all of the following:

- Customer identity is verified.
- At least one active personal checking account exists and has been held for at least 14 days.
- The customer has fewer than five personal savings accounts.
- No account is in collections and no account has a negative balance.
- The customer gave the exact official `account_class`, including the ending `Account`.

If any condition is absent, do not open savings. In particular, request an exact official class ending in `Account` when one was not provided.

When every condition passes, unlock and call `open_bank_account_4821` with the verified user ID, `account_type` `savings`, and the exact selected class. Then review the product's required opening deposit and ask whether the customer authorizes an immediate transfer from a specified checking account. If not, explain that funding by internal transfer or external deposit is required within 30 days or the account will close.

## Internal transfers and balance disposition

Use `transfer_funds_between_bank_accounts_7291` only when the customer explicitly authorizes the transfer and confirms source account, destination account, and a positive USD amount.

Before transfer, confirm both accounts belong to the customer, are distinct, have `OPEN` or `ACTIVE` status, and that the source has sufficient available funds. Review applicable fees, limits, and cutoffs. Unlock the tool and call it with `source_account_id`, `destination_account_id`, and `amount`; verify the result before reporting completion.

For a transfer intended to enable closure, retrieve or otherwise confirm the updated balance and outstanding pending-transaction status before attempting the closure.

## Completion response

Provide a separate result for each requested action. State completed openings, transfers, and closures only after their respective successful tool results. Clearly identify unresolved blockers, including nonzero closure balances, pending transactions, missing disposition authorization, unsatisfied notice, missing approval, failed eligibility, or a missing exact savings selection.

## Optional read-only preflight helper

`scripts/assess_bank_overhaul.py` is optional organization support; it never verifies identity, retrieves live data, authorizes a transfer, unlocks a tool, or executes a banking action. Do not let use of the helper delay an otherwise eligible selected business-checking opening.

Run it with one JSON object on stdin. Input schema:

- `accounts`: required list of account objects. Supported aliases: `account_id`/`id`, `account_class`/`level`, and `balance`/`current_holdings`.
- `user_verified`: required boolean.
- `business_checking_class`: optional selected class string.
- `personal_savings_class`: optional selected class string.
- `now`: optional ISO date/time or `MM/DD/YYYY` date.
- `account_roles`: optional object mapping account IDs to `personal_checking`, `business_checking`, `personal_savings`, or `business_savings`.
- `pending_by_account`: optional object mapping account IDs to booleans or transaction lists.

It emits JSON with `errors`, `business_checking`, `personal_savings`, and `closures`. Any `unknown` or failed check is a live-workflow blocker that must be resolved from current banking data; helper output is not proof of authorization or completion.
