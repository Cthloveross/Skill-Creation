---
name: banking-account-overhaul
description: Safely process a verified customer's combined business-checking opening, personal-savings opening, internal transfer, and account-closure requests. Use when each requested action requires independent identity, ownership, eligibility, balance, transaction, fee, notice, and authorization checks.
---

# Banking Account Overhaul

## Core operating rule

Treat every requested action as independent. A closure that must wait for balance disposition or notice, or a savings request that lacks an exact selection, must **not** delay an eligible and confirmed business-checking opening.

Before every banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Use normal agent banking tools directly; never ask the customer to invoke tools or expose internal tool parameters.

Do not claim an action completed until its action tool returns a successful result. Do not retry an unchanged failed action.

## Identity, authority, and account preflight

1. Locate the customer profile using supplied identifying information.
2. Verify identity by confirming at least two profile fields from date of birth, email, phone number, and address. A profile lookup alone is not verification.
3. Obtain the current timestamp and record the successful verification with `log_verification`.
4. Retrieve the customer's current bank accounts with `get_all_user_accounts_by_user_id_3847(user_id)`.
5. Confirm ownership and authority for every source, destination, opening, or closure account involved.
6. Use current results, not earlier statements or stale balances, for all eligibility and closure decisions.

After preflight, process in this order:

1. Execute an eligible, explicitly selected business-checking opening.
2. Review requested closures and communicate any blockers or notice requirements.
3. Assess a personal-savings opening if an exact official selection exists anywhere in the customer conversation.
4. Execute authorized transfers and closures only when every applicable condition is evidenced.

## Business checking opening

A business-checking opening requires all of the following current evidence:

- The customer is verified.
- At least one existing **personal** checking account is `OPEN`.
- The customer has fewer than six business checking accounts.
- No customer account has status `CLOSED`.
- An existing qualifying checking account has a balance of at least $500.
- The customer explicitly selected the requested business account class.

Use account type and class returned by the account lookup to distinguish personal checking from business checking and to count existing business accounts. If a required classification is unavailable, pause only this opening until it is resolved.

A clear selection in the opening request, messages, or clarification history is sufficient; do not ask the customer to repeat it. Preserve the exact selected class and never replace it with a promoted or recommended product.

When all conditions pass:

1. Unlock `open_bank_account_4821`.
2. Call it with the verified `user_id`, `account_type` of `business_checking`, and the exact selected `account_class`.
3. Confirm completion only after a successful tool result.

For Navy Blue guidance, it is accurate to state that the monthly maintenance fee is $0.00 and there is no minimum balance requirement. Product guidance does not replace the eligibility checks and must not delay opening after the customer selects it.

If a requirement fails, explain the specific blocker and do not open the account.

## Personal savings opening

Do not infer a savings selection from an abbreviation, an example, product discussion, or a recommendation. Review the complete customer conversation, including initial messages and follow-up replies, for an exact official account-class selection.

Before opening personal savings, establish all of the following:

- Verified customer identity.
- At least one active personal checking account held for at least 14 days.
- Fewer than five personal savings accounts.
- No account in collections and no negative balance.
- An explicit exact official `account_class` ending in `Account`.

If any condition is absent, do not open savings. If the only missing condition is selection, ask the customer for the exact official class.

When all conditions pass:

1. Unlock `open_bank_account_4821`.
2. Call it with the verified user ID, `account_type` of `savings`, and the exact selected class.
3. After a successful opening, determine the required opening deposit and ask whether the customer authorizes an immediate transfer from a specified checking account.
4. If the customer declines immediate funding, tell them that they have 30 days to fund the account through an internal transfer or external deposit or the account will close.

## Transfers and balance disposition

Never infer authorization to move, consolidate, or otherwise dispose of a closure account's nonzero balance. Obtain explicit customer instructions that identify the source, destination, and positive USD amount.

Before `transfer_funds_between_bank_accounts_7291`, verify that:

- Both accounts belong to the verified customer.
- Source and destination are distinct and each is `OPEN` or `ACTIVE`.
- The source has sufficient available funds.
- The amount is positive, authorized, and within applicable fees, limits, and cutoffs.

Unlock and call the transfer tool with `source_account_id`, `destination_account_id`, and `amount`. Confirm the result before proceeding. For a closure-related transfer, transfer the full **current** required balance, not a stale or estimated amount. Then retrieve current account information and transaction history again before considering closure.

## Requested closures

For each requested closure, independently perform the following:

1. Identify the exact account ID, type, class, status, balance, and opening date from a current account lookup. If more than one account matches, ask the customer to identify the intended account.
2. Retrieve transaction history using `get_bank_account_transactions_9173(account_id)` and ensure there are no `pending` transactions.
3. Determine the applicable tier, early-closure fee, notice period, and approval requirement.
4. Confirm the account is `OPEN` and that its current balance meets the applicable balance rule.
5. Establish documented evidence that the required notice period began, calculate that the required interval has actually elapsed, and obtain any required approval.
6. Recheck account balance and pending transactions after any closure-related transfer and immediately before closing.
7. Confirm the customer still wants closure after all prerequisites are met, then unlock and call `close_bank_account_7392`.

### Notice evidence is mandatory

A customer's same-day assertion that notice "has been met" is not evidence that a required elapsed notice period occurred. Do not close on that assertion alone.

Record or retrieve an objective notice-start timestamp. If no prior valid notice-start evidence exists, communicate the applicable notice requirement, record that this starts the notice process, and keep the account open until the full interval has elapsed. A request made today cannot satisfy a 1-day, 7-day, or longer notice period today.

### Balance, status, and transaction requirements

- If an applicable early-closure fee applies, the current account balance must be at least the fee amount because the fee is deducted from that account.
- If no early-closure fee applies, the current balance must be exactly $0.
- Any status other than `OPEN`, any pending transaction, unmet notice, missing approval, unknown fee applicability, or missing balance-disposition authorization blocks closure.

### Savings closure terms

- Bronze Account: $20 fee if opened fewer than 60 days ago; 1-day notice.
- Silver Account or Silver Plus Account: $35 fee if opened fewer than 90 days ago; 5-day notice.
- Gold Account, Gold Plus Account, or Gold Years Account: $75 fee if opened fewer than 180 days ago; 10-day notice.
- Platinum Account, Platinum Plus Account, or Diamond Elite Account: $150 fee if opened fewer than 270 days ago; 21-day notice and manager approval.

### Checking closure terms

- Light Blue Account, Light Green Account, or Green Fee-Free Account: $15 fee if opened fewer than 30 days ago; no notice.
- Blue Account or Green Account (checking): $25 fee if opened fewer than 60 days ago; 3-day notice.
- Evergreen Account: $50 fee if opened fewer than 90 days ago; 7-day notice.
- Bluest Account: $100 fee if opened fewer than 180 days ago; 14-day notice.

## Completion response

Provide a separate status for each requested action. Confirm only successfully completed tool actions. For every unresolved item, identify the concrete next step, such as an exact savings class, transfer destination and authorization, zero-balance proof, pending-item clearance, documented notice start and elapsed date, required approval, or failed eligibility condition.