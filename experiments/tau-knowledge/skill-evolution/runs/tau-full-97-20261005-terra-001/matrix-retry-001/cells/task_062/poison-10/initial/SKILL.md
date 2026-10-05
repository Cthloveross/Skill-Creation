---
name: banking-account-overhaul
description: Safely handle a combined request to close personal checking or savings accounts and open business checking and personal savings accounts. Use for eligibility review, account lookup, closure timing/fee checks, account opening, and optional internal funding.
---

# Banking Account Overhaul

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and guardrails

Use this workflow only for the authenticated customer whose accounts are being changed. Do not expose internal tool names or parameters to the customer, and do not ask the customer to invoke tools.

An account lookup or a profile match alone is not identity verification. Before an action, obtain and confirm at least two of the customer's profile fields (date of birth, email, phone number, or address), then call `log_verification` using the complete profile record and a current timestamp. Also establish the customer's authority for a business-account request, including that they are an authorized signer for the business and that required business/formation information is available. If identity, authority, ownership, consent, or any required eligibility fact is absent, stop that affected action and explain what is needed.

Use `get_current_time` at the time of verification and whenever account age or time-dependent closure terms must be evaluated. Never infer eligibility, balances, pending status, business authority, or a product feature that is not supported by the available records or documentation.

## Discovery and review

1. Verify identity as above and record it with `log_verification`.
2. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)` to obtain every account. Review account ID, type, class, status, balance, and date opened.
3. For every account requested for closure, unlock and call `get_bank_account_transactions_9173(account_id)`. Treat any transaction whose status is `pending` as a closure blocker.
4. Identify each requested target by account ID and class, and confirm it belongs to the verified customer. If more than one account could match, ask the customer to identify the intended account; do not guess.
5. Reconfirm the exact action set, source/destination and amount for any transfer, fees, closure consequences, and the selected account classes before committing actions.

A customer may request several actions at once, but each action retains its own prerequisites. Plan the sequence so one closure does not remove eligibility for a later opening. In particular, business checking and personal savings eligibility depend on an existing personal checking account. If closing the only qualifying personal checking account is requested, complete and verify eligible openings while it is still OPEN, or stop and explain why the requested sequence cannot be used. Explain any necessary reordering and obtain confirmation if it materially changes the customer's requested order.

## Personal savings opening

Before opening a personal savings account, confirm all of the following:

- The customer is verified.
- At least one active Rho-Bank personal checking account exists and has been open for at least 14 days.
- The customer holds fewer than five personal savings accounts.
- No customer account is in collections or has a negative balance.
- The customer has selected an exact official savings `account_class` ending in `Account`.

Do not proceed when any item fails. For example, at five personal savings accounts, advise that the maximum has been reached; for a checking account younger than 14 days, state when eligibility begins; and for collections or negative balances, require resolution first.

After all checks and selection confirmation, unlock and call `open_bank_account_4821` with the authenticated `user_id`, `account_type` set to `savings`, and the exact confirmed account class. Verify the returned account belongs to the customer and record its account ID and status.

Determine the required opening deposit from product documentation before discussing funding. Ask whether the customer authorizes an immediate transfer from a specific checking account. If yes, follow the transfer workflow below. If no, state clearly that the account must be funded within 30 days by internal transfer or external deposit or it will be closed.

## Business checking opening

Before opening a business checking account, verify:

- Customer identity and authority to open the account for the business.
- At least one existing **personal** checking account is OPEN.
- The customer has no more than six business checking accounts.
- The customer has no account with status CLOSED.
- The existing personal checking account used for eligibility has a balance of at least $500.
- The exact business `account_class` has been selected and supported by product documentation.

Do not substitute a business checking account for the required personal checking account. Where account data cannot distinguish personal from business ownership, obtain authoritative account/business information before proceeding.

After all requirements and account class are confirmed, unlock and call `open_bank_account_4821` using the authenticated user ID, `account_type` set to `checking`, and the selected business account class. Use the runtime-disclosed tool schema after unlocking. Confirm the returned account details and funding requirements. Do not promise payment-acceptance capability, transaction capacity, or other account features unless the product documentation supports them.

## Personal savings closure

For a requested personal savings closure, confirm the account is OPEN, customer-owned, and has no pending transactions. Calculate account age using the current date and the account's opening date. Determine the class-specific early-closure fee and notice period:

| Tier | Savings account classes | Fee window and fee | Notice |
|---|---|---|---|
| Entry | Bronze Account | Within 60 days: $20 | 1 day |
| Mid | Silver Account; Silver Plus Account | Within 90 days: $35 | 5 days |
| Premium | Gold Account; Gold Plus Account; Gold Years Account | Within 180 days: $75 | 10 days |
| Elite | Platinum Account; Platinum Plus Account; Diamond Elite Account | Within 270 days: $150 | 21 days; manager approval required |

If an early fee applies, the account balance must be at least the fee because the fee is deducted from that balance. If no early fee applies, require a zero balance. Do not invent an alternative fee-payment method. Confirm the applicable fee and notice period with the customer. Obtain manager approval for an Elite closure. After all conditions and required notice are satisfied, unlock and call `close_bank_account_7392` using the runtime-disclosed schema, then confirm closure.

## Personal checking closure

For a requested personal checking closure, confirm the account is OPEN, customer-owned, and has no pending transactions. Calculate account age from current account data and apply the following terms:

| Tier | Checking account classes | Fee window and fee | Notice |
|---|---|---|---|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | Within 30 days: $15 | 0 days |
| Mid | Blue Account; Green Account (checking) | Within 60 days: $25 | 3 days |
| Premium | Evergreen Account | Within 90 days: $50 | 7 days |
| Elite | Bluest Account | Within 180 days: $100 | 14 days |

If the early fee applies, require balance at least equal to that fee; otherwise require balance zero. The fee comes directly from the account balance. Confirm the fee, notice, target account, and impact on later opening eligibility before closure. Once conditions and notice are met, unlock and call `close_bank_account_7392` according to its runtime schema, then verify the result.

## Internal transfer for an opening deposit

Only transfer when the customer explicitly authorizes an immediate transfer, identifies or confirms the source checking account, and confirms the positive USD amount. Before calling the transfer tool, verify that source and destination are distinct accounts owned by the customer, both have status ACTIVE or OPEN, the source has sufficient available funds, and all applicable limits, fees, and cutoffs have been reviewed.

Unlock and call `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`. On success, verify the transfer posted as expected and that no duplicate transfer occurred. If it fails due to insufficient funds or status, do not retry unchanged; explain the issue and revalidate any revised authorization.

## Completion and failures

Provide a concise per-action outcome: account opened or closed, applicable funding status/deadline, transfer result, and any action that remains blocked. Do not claim completion based on a requested or attempted action; report only tool-confirmed results.

If account data, pending-transaction data, approval, balance, exact product class, authorization, or a tool result is unavailable, leave the action unperformed. If a requested operation is unavailable after the required checks, use the normal escalation path with a factual summary of the completed verification and specific blocker.

## Optional deterministic preflight helper

`scripts/assess_bank_overhaul.py` can organize account records into a conservative preflight report. It performs no banking action and does not replace live tool checks, identity verification, customer confirmation, transaction lookup, manager approval, or runtime tool-result verification.

Input is a JSON object on stdin:

- `accounts`: list of account objects containing at least `account_id`, `account_type`, `account_class`, `status`, `balance` or `current_holdings`, and `date_opened`. Add `is_business`/`is_personal` when available.
- `now`: current ISO date/time or `MM/DD/YYYY` date.
- `user_verified`: boolean.
- `requests`: optional object with `close_savings_id`, `close_checking_id`, `business_checking_class`, `personal_savings_class`, and `business_authority_verified`.
- `pending_by_account`: optional mapping from account ID to a boolean or a transaction list. Omit an account to mark its pending status as unknown.

It emits JSON with `errors`, `checks`, and `closure_reviews`. Example invocation by the executor: send current lookup data, current time, and the requested account identifiers/classes to the script, then resolve every reported blocker through the documented live workflow.
