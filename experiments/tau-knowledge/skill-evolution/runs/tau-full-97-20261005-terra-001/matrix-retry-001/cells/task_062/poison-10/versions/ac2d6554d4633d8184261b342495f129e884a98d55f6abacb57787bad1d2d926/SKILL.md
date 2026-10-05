---
name: banking-account-overhaul
description: Safely handle a verified customer's combined request to open business checking or personal savings accounts, transfer internal funds, and close personal checking or savings accounts. Use when each requested banking action has separate eligibility, ownership, balance, transaction, fee, notice, and confirmation requirements.
---

# Banking Account Overhaul

## Core rule

Treat every requested opening, transfer, and closure as an independent action. A blocked closure must not delay an independently eligible account opening. Conversely, do not close a personal checking account before completing an opening that depends on that personal checking account for eligibility.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Use only the verified customer's accounts. Do not expose internal tool names or parameters to the customer or ask the customer to invoke bank tools.

## Verify the customer and retrieve accounts

1. Locate the customer profile from supplied identifying information.
2. Confirm two profile fields with the customer from date of birth, email, phone number, and address. A profile lookup alone is not identity verification.
3. Obtain the current timestamp with `get_current_time` and create the audit record with `log_verification` using the verified profile fields and timestamp.
4. Retrieve all bank accounts with `get_all_user_accounts_by_user_id_3847(user_id)`.
5. Confirm that every account involved in an opening, transfer, or closure belongs to the verified customer. Review available authority or ownership information for a business request; resolve contradictions before acting, but do not invent prerequisites not present in the applicable procedure.

## Priority sequence for mixed requests

After identity verification and the account lookup, use this order:

1. Evaluate and execute a customer-selected business-checking opening immediately if eligible.
2. Review each requested closure, including transaction history and balance blockers.
3. Evaluate personal-savings opening only when the customer has supplied an exact official savings class.
4. Carry out an authorized balance disposition, then close an account only after every closure requirement has been met.

Do not wait for a blocked closure, a missing savings selection, or a customer decision about another action before executing a selected and eligible business-checking opening.

## Open a selected business checking account

Evaluate these requirements from the verified account list:

- The customer is verified.
- At least one existing **personal** checking account is `OPEN`.
- The customer has fewer than six business checking accounts.
- No account is `CLOSED`.
- An existing qualifying personal checking account has a balance of at least $500.
- The customer selected a supported business-checking `account_class`.

Use available account classification data to distinguish personal and business checking. If the records are genuinely ambiguous, obtain the missing classification rather than guessing.

Once these requirements pass, do not re-ask for an already confirmed class and do not substitute a promotion or recommendation for the customer's choice. Unlock `open_bank_account_4821`, then call it through the normal agent-tool interface with:

- `user_id`: the verified customer's ID
- `account_type`: `checking`
- `account_class`: the exact selected business-checking class

Report the account as opened only after a successful tool result. If the tool fails, report the failure and do not claim completion or retry unchanged parameters.

## Review requested closures

For each closure request:

1. Identify the exact account by account ID and class in the verified customer's account list. If multiple accounts match the request, ask which one is intended.
2. Retrieve its history with `get_bank_account_transactions_9173(account_id)`. Any transaction whose status is `pending` blocks closure.
3. Confirm the account is `OPEN`, its current balance, its opening date, the current date, applicable early-closure fee, required notice, and any required approval.
4. Obtain and document the required notice and customer confirmation. For elite savings, obtain manager approval.
5. Unlock and call `close_bank_account_7392` only after all requirements are satisfied.

A nonzero balance is not automatically transferable or disposable. Obtain explicit customer instructions for disposition of a balance before transferring it. If the closure prerequisites are not met, keep the account open, explain the blocker, and state what is needed next.

### Personal savings closure terms

| Account class | Early-closure window and fee | Notice | Additional requirement |
| --- | --- | ---: | --- |
| Bronze Account | under 60 days: $20 | 1 day | — |
| Silver Account; Silver Plus Account | under 90 days: $35 | 5 days | — |
| Gold Account; Gold Plus Account; Gold Years Account | under 180 days: $75 | 10 days | — |
| Platinum Account; Platinum Plus Account; Diamond Elite Account | under 270 days: $150 | 21 days | manager approval |

### Personal checking closure terms

| Account class | Early-closure window and fee | Notice |
| --- | --- | ---: |
| Light Blue Account; Light Green Account; Green Fee-Free Account | under 30 days: $15 | 0 days |
| Blue Account; Green Account (checking) | under 60 days: $25 | 3 days |
| Evergreen Account | under 90 days: $50 | 7 days |
| Bluest Account | under 180 days: $100 | 14 days |

If an early-closure fee applies, the account balance must be at least that fee because it is deducted from the account. If no early fee applies, the account balance must be exactly $0. There is no alternative fee-payment method.

## Open personal savings only after exact selection

Do not infer a personal-savings selection from an abbreviated name, an example, or a product recommendation. Before opening, confirm all of the following:

- Customer identity is verified.
- At least one active personal checking account exists and has been held for at least 14 days.
- The customer holds fewer than five personal savings accounts.
- No account is in collections and no account has a negative balance.
- The customer gave the exact official `account_class`, including the ending `Account`.

When all requirements pass, unlock and call `open_bank_account_4821` with the verified user ID, `account_type` set to `savings`, and the exact selected class. Review the product's required opening deposit. Ask whether the customer authorizes an immediate deposit from a specified checking account:

- If authorized, follow the internal transfer workflow.
- If not authorized, explain that the account must be funded by internal transfer or external deposit within 30 days or it will be closed.

## Internal transfer workflow

Use `transfer_funds_between_bank_accounts_7291` only after the customer explicitly authorizes the transfer and confirms the source account, destination account, and positive USD amount.

Before calling it, confirm both accounts belong to the customer, are distinct, and are `OPEN` or `ACTIVE`; the source has sufficient available funds; and applicable fees, limits, and cutoffs have been reviewed. Unlock the tool and call it with `source_account_id`, `destination_account_id`, and `amount`. Verify the result before reporting completion and do not retry an unchanged failed transfer.

## Completion communication

Give a per-action result. Say an account was opened, transferred, or closed only after the corresponding successful tool result. Clearly identify blockers such as a nonzero balance, pending transactions, missing exact savings selection, unpaid notice, missing approval, or failed eligibility.

## Read-only preflight helper

`scripts/assess_bank_overhaul.py` organizes account data already retrieved at runtime. It does not verify identity, establish authority, retrieve transaction histories, authorize funds movement, unlock tools, or execute banking actions.

Run it by sending one JSON object on stdin:

- `accounts`: list of account objects. Supported aliases are `account_id`/`id`, `account_class`/`level`, and `balance`/`current_holdings`.
- `now`: ISO timestamp/date or `MM/DD/YYYY` date.
- `user_verified`: boolean.
- `requests`: optional object with `business_checking_class`, `personal_savings_class`, `close_savings_id`, and/or `close_checking_id`.
- `account_roles`: optional mapping of account ID to `personal_checking`, `business_checking`, `personal_savings`, or `business_savings` when the retrieved records do not identify the role.
- `pending_by_account`: optional mapping of account ID to a boolean or transaction list.
- `notice_satisfied_by_account`: optional mapping of closure account ID to a boolean.
- `manager_approved_by_account`: optional mapping of closure account ID to a boolean.

It emits JSON with `errors`, `checks`, and `closure_reviews`. Treat unknown or failed checks as blockers to resolve using the live banking workflow; do not treat this helper as a substitute for required tool checks or customer confirmation.
