---
name: banking-account-overhaul
description: Execute a verified customer's combined bank-account closure, business-checking opening, personal-savings opening, and internal-transfer requests. Use when each requested action needs separate identity, ownership, eligibility, balance, fee, pending-transaction, notice, and authorization checks.
---

# Banking Account Overhaul

## Core rule: execute independent eligible requests

Treat each requested action independently. A blocked closure, missing savings selection, or follow-up product discussion must **not** delay an independently eligible, customer-confirmed business-checking opening.

When the customer has selected a business checking class and the documented checks pass, immediately unlock and call the opening tool in the same workflow turn. Do not merely say it is eligible, ask the customer to repeat a selection already present in the request or clarifications, or spend remaining execution budget reviewing blocked requests first.

Before every banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Do not expose internal tool parameters or ask the customer to invoke tools.

## Identity and account preflight

1. Locate the customer profile from supplied identifying information.
2. Verify identity by confirming two profile fields among date of birth, email, phone number, and address; a lookup alone is not verification.
3. Get the current time and call `log_verification` with the verified profile data and timestamp.
4. Unlock and use `get_all_user_accounts_by_user_id_3847(user_id)` to obtain current account IDs, types, classes, status, balances, and opening dates.
5. Confirm the customer owns every account involved. Resolve an authority or ownership conflict before acting.

Use current tool results, not assumptions, for eligibility and closure decisions. Do not claim success until the relevant action tool returns success, and do not retry an unchanged failed action.

## Required order for a mixed request

After successful identity verification and account lookup:

1. Assess and execute the selected business-checking opening if eligible.
2. Review each requested closure and identify blockers.
3. Assess personal-savings opening only if an exact official savings class was selected.
4. Execute transfers and closures only after their independent requirements pass.

This ordering is mandatory because account opening can be complete even when requested closures remain blocked.

## Business checking opening

A selected business checking account is eligible only when the account record confirms all of the following:

- Customer identity is verified.
- At least one existing **personal** checking account is `OPEN`.
- The customer has fewer than six business checking accounts.
- No customer account has status `CLOSED`.
- An existing qualifying personal checking account has a balance of at least $500.
- The customer explicitly selected the business `account_class`.

Use returned account type/class information to distinguish and count personal and business accounts. Do not request redundant classification if the record establishes it. If a necessary classification is genuinely unavailable, pause only that opening until it is resolved.

Once all checks pass:

1. Preserve the exact customer-selected class; do not substitute a promotion or recommendation.
2. Unlock `open_bank_account_4821`.
3. Call it through the normal agent-tool interface with:
   - `user_id`: verified customer's user ID
   - `account_type`: `checking`
   - `account_class`: exact selected business class
4. Report completion only after a successful result.

A customer choice such as `Navy Blue` is an explicit selection, not a request for another recommendation. Navy Blue product guidance may accurately state that it has a $0.00 monthly maintenance fee and no minimum balance requirement; those facts do not replace eligibility checks or delay opening after selection.

If a condition fails, explain the specific failed condition and do not open the account.

## Requested closures

For each requested closure:

1. Identify the exact account ID and class from the verified account list. If multiple accounts fit, ask which account is intended.
2. Unlock and call `get_bank_account_transactions_9173(account_id)`. Any transaction with status `pending` blocks closure.
3. Confirm status is `OPEN`, current balance, opening date, applicable early-closure fee, notice period, and any required approval.
4. Confirm required notice and closure confirmation are satisfied.
5. Unlock and call `close_bank_account_7392` only after every requirement is satisfied.

Never infer authorization to move or dispose of a nonzero closure balance. If the balance must be reduced, request explicit instructions identifying the destination and amount before any transfer. Keep the account open and clearly explain the blocker until all requirements pass.

### Savings closure terms

- Bronze Account: $20 fee if under 60 days; 1-day notice.
- Silver Account or Silver Plus Account: $35 fee if under 90 days; 5-day notice.
- Gold Account, Gold Plus Account, or Gold Years Account: $75 fee if under 180 days; 10-day notice.
- Platinum Account, Platinum Plus Account, or Diamond Elite Account: $150 fee if under 270 days; 21-day notice and manager approval.

### Checking closure terms

- Light Blue Account, Light Green Account, or Green Fee-Free Account: $15 fee if under 30 days; no notice.
- Blue Account or Green Account (checking): $25 fee if under 60 days; 3-day notice.
- Evergreen Account: $50 fee if under 90 days; 7-day notice.
- Bluest Account: $100 fee if under 180 days; 14-day notice.

If an early fee applies, the account balance must at least cover that fee because it is deducted directly from the account. If no early fee applies, the balance must be exactly $0. Status other than `OPEN`, a pending transaction, unmet notice, or missing required approval also blocks closure.

## Personal savings opening

Do not infer a savings selection from an abbreviation, example, product discussion, or recommendation. Before opening personal savings, confirm:

- Verified customer identity.
- At least one active personal checking account held for at least 14 days.
- Fewer than five personal savings accounts.
- No account in collections and no negative balance.
- An exact official selected `account_class` ending in `Account`.

If any condition is missing, do not open savings. Ask for the exact official class when that is the missing item.

When all requirements pass, unlock and call `open_bank_account_4821` with the verified user ID, `account_type` set to `savings`, and the exact selected class. Then determine the required opening deposit and ask whether the customer authorizes an immediate transfer from a specified checking account. If not, tell them funding by internal transfer or external deposit is required within 30 days or the account will close.

## Transfers and closure-balance disposition

Use `transfer_funds_between_bank_accounts_7291` only after the customer explicitly authorizes the transfer and identifies the source account, destination account, and positive USD amount.

Before transfer, verify both accounts belong to the customer, are distinct, have `OPEN` or `ACTIVE` status, source available funds are sufficient, and applicable fees, limits, and cutoffs are acceptable. Unlock the tool, call it with `source_account_id`, `destination_account_id`, and `amount`, then verify the result. For a closure-related transfer, recheck the balance and pending activity before attempting closure.

## Completion response

Give a separate status for every requested action. Confirm only actions with successful tool results. Clearly identify unresolved items, such as a nonzero closure balance, pending transaction, missing balance-disposition authorization, notice period, approval, failed eligibility condition, or missing exact savings class.
