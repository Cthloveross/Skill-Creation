---
name: banking-account-overhaul
description: Handle a verified customer's combined request to review or close personal checking/savings accounts, open a selected business checking account, and open a selected personal savings account. Use when account eligibility, closure blockers, product selection, and optional internal funding must be handled safely and independently.
---

# Banking Account Overhaul

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Core operating rule

Treat each requested opening, transfer, and closure as a separate action with its own prerequisites. Do not let a blocked closure prevent an independently eligible opening. Conversely, do not close a personal checking account if doing so would remove eligibility for a requested opening that has not yet been completed.

Use only the verified customer's accounts. Do not expose internal tool names or parameters to the customer and do not ask the customer to call bank tools.

## Identity, ownership, and request confirmation

1. Locate the customer profile from the supplied identifying information.
2. Confirm at least two profile fields from date of birth, email, phone number, and address, then obtain a current timestamp and create the verification record with `log_verification`.
3. Retrieve all bank accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Confirm that each requested source, destination, or closure target belongs to the verified customer.
4. Confirm the customer is requesting the business account for their business and review any available ownership or authority information. Do not invent an additional document, authorized-signer, or formation-document prerequisite when the applicable business-checking procedure does not require one. If available records contradict the customer's authority or ownership, stop the affected action and resolve that discrepancy.
5. Confirm the selected product class and any required transfer amount before executing the affected action.

A profile lookup by itself is not identity verification. A customer may have already selected an account class in the conversation; do not ask them to select it again merely because other requested actions are blocked.

## Review requested closures first, but do not execute blocked closures

For each account the customer wants to close:

1. Identify the exact account in the account lookup by its ID and class. If more than one account could match, ask the customer to identify the target.
2. Retrieve its transaction history with `get_bank_account_transactions_9173(account_id)`. A transaction with `status` `pending` blocks closure.
3. Confirm account status is `OPEN`, review current balance, retrieve current time, and calculate account age from `date_opened`.
4. Determine the applicable early-closure fee and notice period below.
5. Do **not** call `close_bank_account_7392` until all closure requirements, required notice, customer confirmation, and applicable approval are satisfied.

A nonzero balance is not automatically transferable or disposable. When a balance must be reduced, obtain the customer's explicit disposition instructions and, where an internal transfer is requested, follow the transfer workflow. Do not close the account merely because the customer asked to close it.

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

For either type of closure, if an early fee applies, the account balance must be at least the fee because the fee is deducted from that account. If no early fee applies, the balance must be exactly $0. There is no alternative fee-payment method. Confirm the applicable fee and notice with the customer. Elite savings closures also require manager approval. Only then unlock and call `close_bank_account_7392` using its disclosed runtime schema and report only a tool-confirmed result.

## Open selected business checking promptly when eligible

Once identity verification and the account lookup are complete, evaluate business-checking eligibility independently of any blocked closures:

- The customer is verified.
- At least one existing **personal** checking account has status `OPEN`.
- The customer has fewer than six business checking accounts.
- No account in the retrieved account list has status `CLOSED`.
- At least one qualifying existing personal checking account has a balance of at least $500.
- The customer selected an exact supported business checking `account_class`.

Do not replace the required personal checking account with a business checking account. If ownership/category information is ambiguous, use available account details to resolve it; do not guess.

After all listed checks pass and the customer has selected the class, immediately unlock and call `open_bank_account_4821` with:

- `user_id`: verified customer's user ID
- `account_type`: `checking`
- `account_class`: the exact customer-selected business checking class

Do not postpone this action because a separate requested closure has a balance or pending-transaction blocker. Do not substitute a promotional product for the class the customer selected. Confirm the new account only from the tool result.

## Open personal savings only after an exact selection

Before opening personal savings, verify all of the following:

- The customer is verified.
- At least one active personal Rho-Bank checking account exists and has been held at least 14 days.
- The customer holds fewer than five personal savings accounts.
- No account is in collections or has a negative balance.
- The customer supplied the exact official savings `account_class`, including the ending `Account`.

A general preference or abbreviated name is not an exact official savings selection. Do not open a savings account until the customer supplies the exact class. Do not infer a selection from examples presented by the agent.

Once eligible and selected, unlock and call `open_bank_account_4821` with `account_type` `savings`, the verified user ID, and the exact selected class. Review product documentation for its required opening deposit. Ask whether the customer authorizes an immediate transfer from a specified checking account:

- If yes, use the transfer workflow below after confirming the amount and source.
- If no, tell the customer that the account must be funded within 30 days by internal transfer or external deposit or it will be closed.

## Internal transfer workflow

Use `transfer_funds_between_bank_accounts_7291` only when the customer explicitly authorizes the transfer and confirms the source account, destination account, and positive USD amount.

Before calling it, confirm that both accounts belong to the customer, are distinct, and are `OPEN` or `ACTIVE`; that the source has sufficient available funds; and that relevant fees, limits, and cutoffs have been reviewed. Unlock and call the tool with `source_account_id`, `destination_account_id`, and `amount`. Verify the posted result and avoid duplicate transfers. If it fails, do not retry unchanged; explain the failure and obtain/validate any revised instruction.

## Sequencing and completion

A safe default sequence is:

1. verify identity and retrieve the account list;
2. review closure accounts and transaction histories for blockers;
3. perform any selected, eligible business-checking opening while qualifying personal checking remains open;
4. perform an eligible personal-savings opening only after its exact class is selected;
5. complete authorized balance disposition and only then close accounts whose closure requirements are met.

Provide a per-action outcome. State which accounts were opened or closed only after successful tool results, and identify blockers such as nonzero balance, pending transactions, missing selection, elapsed notice, insufficient information, or missing approval. When a closure is blocked by balance, ask for disposition instructions; when savings is blocked by selection, ask for the exact official account class.

## Deterministic preflight helper

`scripts/assess_bank_overhaul.py` is a read-only aid for organizing retrieved account data. It does not verify identity, determine authority, retrieve transactions, authorize a transfer, unlock tools, or execute any banking action.

Send one JSON object on stdin with:

- `accounts`: a list of account objects. The helper accepts common aliases: `account_id`/`id`, `account_class`/`level`, and `balance`/`current_holdings`.
- `now`: ISO timestamp/date or `MM/DD/YYYY` date.
- `user_verified`: boolean.
- `requests`: optional object containing `business_checking_class`, `personal_savings_class`, `close_savings_id`, and/or `close_checking_id`.
- `account_roles`: optional mapping from account ID to `personal_checking`, `business_checking`, or another role. Supply it whenever account records do not clearly distinguish personal and business checking.
- `pending_by_account`: optional mapping from account ID to a boolean or a transaction list. Omitted requested closure accounts are reported as unknown.

It writes one JSON object to stdout with `errors`, `checks`, and `closure_reviews`. For example, the executor can supply live account records, classifications, transaction results, and the customer selections, then resolve all reported blockers through the live workflow. Never use a helper report in place of required bank-tool checks or customer confirmation.
