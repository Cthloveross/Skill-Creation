---
name: personal-checking-transition
version: 1.0.0
description: Safely assists a verified customer who wants to close a personal checking account, open a replacement checking account, and/or later open savings. Use for account-transition requests involving closure eligibility, early-closure fees, checking/savings opening eligibility, and linked-account overdraft protection.
---

# Personal Checking Transition

Use this Skill to carry out a customer-requested sequence of personal-account changes without assuming that customer statements substitute for required account checks. The customer may choose the order of requested actions, subject to eligibility and closure requirements.

## Required identity and audit step

1. Identify the customer using a supplied email or exact case-sensitive name with the applicable user lookup tool.
2. Verify identity by having the customer confirm **two of four** profile fields: date of birth, email, phone number, and address. Do not reveal unconfirmed fields as authentication prompts; ask the customer to provide them.
3. Get the current timestamp and call `log_verification` with the complete returned profile fields and timestamp after two fields match.
4. Do not make account changes until verification is successfully logged.

## Obtain authoritative account facts

Unlock and use `get_all_user_accounts_by_user_id_3847` for the verified customer. Use the returned account records, not only the customer's recollection, to determine account IDs, type/class, status, balance, and opening date.

Before any closure, inspect the target account specifically. Confirm it is the customer-selected personal checking account and determine:

- `status` is `OPEN`;
- current balance is appropriate for closure;
- opening date and tier, so the early-closure window can be calculated from the current date; and
- that no pending transactions remain. If pending status is available in the account/activity information, use it. If the available records cannot establish this requirement, tell the customer closure cannot yet be safely completed and obtain the needed bank-supported account/pending-activity check rather than guessing.

## Closure rules

Use the account class to select the rule below. An early fee applies when the closure date is within the stated number of days after opening.

| Tier / account class | Early fee | Early window | Notice period |
|---|---:|---:|---:|
| Entry: Light Blue Account, Light Green Account, Green Fee-Free Account | $15 | 30 days | 0 days |
| Mid: Blue Account, Green Account (checking) | $25 | 60 days | 3 days |
| Premium: Evergreen Account | $50 | 90 days | 7 days |
| Elite: Bluest Account | $100 | 180 days | 14 days |

Apply these requirements exactly:

- The account must be `OPEN` and have no pending transactions.
- If an early fee applies, the balance must be at least that fee. The fee is deducted from the account; do not offer another payment method.
- If no early fee applies, the balance must be exactly $0.
- Explain the applicable fee and notice period before proceeding. Follow any required notice handling exposed by the closing tool or workflow; do not claim immediate closure where a notice requirement prevents it.

After all requirements are met and the customer still wants to proceed, unlock `close_bank_account_7392` and call it with the target account identifier using the tool's exposed schema. Report the actual result. Never retry a closure that returns an unknown/indeterminate outcome.

If a prerequisite fails, do not call the closure tool. Clearly state the unmet condition (for example, pending transactions, nonzero balance without an applicable fee, or insufficient balance to pay an early fee) and what must happen before closure can continue.

## Opening a personal checking account

Only open a replacement checking account after the customer has selected the exact full official `account_class` string ending in `Account` and has confirmed they want it opened.

Before opening, verify from authoritative records that:

1. the customer is verified;
2. the customer is at least 18;
3. the customer has no more than four personal checking accounts; and
4. the customer has had no checking account closed for cause in the preceding six months.

If eligible, unlock `open_bank_account_4821` and call it with the verified `user_id`, `account_type` of `checking`, and the exact confirmed `account_class`. Confirm the tool result and retain the new account ID for any later supported action.

### Overdraft-protection request

For a customer who requests automatic linked-account overdraft transfers, explain that Blue Account offers this option for **$12.50 per protection-triggered transfer**. Enrollment requires an eligible funding account to link and acceptance of the fee disclosure. Do not represent the service as enabled merely because a Blue Account was opened, and do not invent an enrollment action if no supported tool is available.

If the customer has no eligible linked funding account yet, explain that protection cannot be enrolled until one exists. The customer may open checking now and arrange the link later when eligible.

## Opening personal savings

Savings is optional unless the customer asks to open it now. Do not force it ahead of a requested checking closure.

Before opening savings, check all of the following from verified profile and current account data:

1. verified customer;
2. at least one active Rho-Bank checking account;
3. that checking account has been open at least 14 days;
4. fewer than five personal savings accounts;
5. no accounts in collections and no negative balances.

Also obtain the customer-selected exact full savings `account_class` ending in `Account`. If eligible and authorized, call the unlocked `open_bank_account_4821` with `account_type` `savings`.

For a customer seeking the highest documented rate among the supplied offerings, describe Gold Account accurately: 5.5% APY and a $10,000 minimum balance. Do not say it is universally the highest rate unless the available product information supports that comparison.

After a savings account is opened, ask whether the customer authorizes an immediate opening-deposit transfer from a checking account. Only if they say yes, unlock and use `transfer_funds_between_bank_accounts_7291` with the selected source checking account, new destination savings account, and authorized amount. If they decline, tell them the account must be funded within 30 days via internal transfer or external deposit or it will be closed.

## Sequence counseling

Respect the requested order, but explain consequences before acting. A savings account requires an active checking account held for at least 14 days. Therefore, if the customer closes their only seasoned checking account before opening savings, opening a brand-new replacement checking account does not make them savings-eligible until that new checking account reaches 14 days of tenure. There is no requirement to start with savings; preserving the existing eligible checking account until savings is opened is simply an option if the customer wants savings immediately.

A customer may instead close the old account first (if closure requirements are met), open replacement checking, and defer savings. In that sequence, accurately disclose the likely 14-day wait for savings eligibility and the lack of a linked funding account for overdraft protection until an eligible account is available.

## Communication and safety

- Ask only for information still needed; do not ask a customer to redisclose facts already authoritatively retrieved.
- Do not infer account age, pending activity, verification, cause-of-closure history, account counts, or balances from unsupported customer statements.
- Do not use scripts as a substitute for bank actions. All state-changing actions must use the declared normal banking tools.
- State completed actions, actual fees, relevant deadlines, and any deferred prerequisite in the final customer response.
- If the request cannot be completed with the supported tools or required facts cannot be confirmed, explain the limitation and, when appropriate, transfer using the applicable supported reason rather than fabricating completion.
