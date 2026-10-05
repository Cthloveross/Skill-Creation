---
name: personal-account-replacement-and-savings-opening
description: Safely replace a personal checking account, open and fund a personal savings account, and explain eligible product trade-offs. Use for authenticated customers requesting checking closure/opening, savings opening, internal funding, or external funding.
---

# Personal Account Replacement and Savings Opening

Use this workflow for a customer who wants to close or replace a personal checking account and/or open a personal savings account. It separates eligibility checks, customer confirmations, and agent-performed banking actions. Do not state that an action is complete unless its tool call succeeded.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Available documented agent actions

Unlock the applicable documented agent tool before calling it. Use the signature exposed by the runtime after unlock; do not invent additional fields or assume a successful result.

- `get_all_user_accounts_by_user_id_3847(user_id)`: retrieve account ID, type, class, status, balance, and opening date. Use before account opening, closure, or internal transfers.
- `get_bank_account_transactions_9173(account_id)`: retrieve transactions, including pending status. Use to validate closure prerequisites.
- `open_bank_account_4821(user_id, account_type, account_class)`: open a confirmed checking or savings product. `account_type` is `checking` or `savings`; `account_class` must be the complete official product name ending in `Account`.
- `close_bank_account_7392`: close an eligible account. Its exact call fields must be taken from the unlocked tool interface.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`: fund a new savings account only when the customer authorizes an internal transfer and all transfer preconditions hold.

No documented agent tool enrolls overdraft protection or links its funding account. Where the product documentation describes enrollment in account settings, direct the customer to those settings after the relevant accounts exist; do not claim the service was enabled or linked by an agent.

## Required identity and authority gate

1. Locate a potential customer record only from the identifier the customer supplied. A name lookup is not authentication.
2. Ask the customer to confirm at least two of the four profile fields: date of birth, email, phone number, and address. Do not reveal unconfirmed values in the prompt.
3. After two fields match, obtain the current time and call `log_verification` with the complete record and timestamp.
4. Confirm the requester is the account holder and is authorizing each requested closure, opening, and any transfer.
5. Stop and request the missing confirmation if identity or authority is not established.

## Gather and validate account state

After verification, unlock and call the all-accounts tool. Obtain enough system evidence to validate the requested actions rather than relying solely on a customer assertion.

For the checking account to be closed, retrieve its transactions and confirm no transaction has `status: pending`. For every opening, determine the current number and status of the customer’s personal checking and savings accounts, balances, dates opened, and any account-history information needed for closed-for-cause checks. If the account lookup cannot establish an eligibility condition, do not open the account; obtain the missing internal record or explain that the request cannot yet be completed.

Run the packaged validator with normalized account data. It identifies missing evidence and applies the documented account-count, tenure, negative-balance, early-fee, and closure checks.

```text
run_skill_script(
  relative_path="scripts/assess_account_change.py",
  input_json={
    "today": "YYYY-MM-DD",
    "identity_verified": true,
    "authority_confirmed": true,
    "date_of_birth": "MM/DD/YYYY",
    "closed_for_cause_last_6_months": false,
    "accounts": [ ...normalized account records... ],
    "closure_account_id": "optional existing account id",
    "notice_satisfied": true
  }
)
```

The script emits JSON with `checking_open`, `savings_open`, and `closure` verdicts. Proceed only where the relevant `eligible` value is true. Its output is a validation aid, not a substitute for the account and transaction tool results.

### Opening eligibility

**Personal checking** requires all of the following:

- verified customer;
- age 18 or older;
- fewer than four existing personal checking accounts before the new one is opened, so the opening will not create more than four;
- no checking account closed for cause in the prior six months; and
- an explicitly confirmed full official checking `account_class`.

**Personal savings** requires all of the following:

- verified customer;
- at least one active Rho-Bank checking account held for at least 14 days;
- fewer than five existing personal savings accounts;
- no accounts in collections and no negative account balances; and
- an explicitly confirmed full official savings `account_class`.

Preserve an existing qualifying checking account until the savings opening succeeds. A newly opened checking account does not itself satisfy the 14-day savings-tenure requirement.

### Checking closure validation

Before closing, verify:

- account status is `OPEN`;
- no pending transactions exist;
- applicable notice requirements are satisfied; and
- balance is exactly $0 if no early-closure fee applies, or is at least the applicable fee if it does.

Closure tiers are:

| Account class | Early fee and period | Notice |
|---|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | $15 within 30 days | 0 days |
| Blue Account, Green Account (checking) | $25 within 60 days | 3 days |
| Evergreen Account | $50 within 90 days | 7 days |
| Bluest Account | $100 within 180 days | 14 days |

The fee is deducted only from the closing account. Do not collect it from another account or close an early account with insufficient funds. If the account is still in the fee period and cannot cover the fee, explain the required balance and leave it open.

## Product matching and customer confirmation

Discuss relevant choices without representing unsupported features. Before opening, recap the exact class, material fees, balance requirements, and requested features, then obtain confirmation of each full class name.

For a customer with $10,000, no eligible credit card, a requirement for an ATM-fee rebate on savings, and a need for linked overdraft transfers:

- **Blue Account** is the supported replacement checking choice when the customer specifically needs overdraft protection funded from a linked account. Each protection-triggered transfer costs $12.50. It has a $20 monthly maintenance fee, waived with a $625 minimum daily balance. The customer must enroll and choose the linked funding account in account settings after opening.
- **Gold Account** is the supported savings choice when the customer must keep $10,000 for the year and also requires savings ATM-fee rebates. It has 5.5% APY, daily compounding, monthly interest crediting, a $5,000 opening deposit minimum, a $10,000 ongoing minimum balance, up to 20 monthly withdrawals, and up to $30 in monthly ATM-fee rebates.
- Do not describe Gold as the highest rate without context. Higher-rate documented tiers require balances the $10,000 plan cannot maintain (Gold Plus: $10,000 opening and $25,000 ongoing; Platinum: $25,000 opening and $50,000 ongoing; Platinum Plus: $50,000 opening and $100,000 ongoing). Gold Plus also has no documented ATM-fee rebate in the supplied product terms. Silver Plus has documented ATM rebates but a lower 3.0%/4.5% tiered rate.
- A Blue Account does not have a documented Gold Account linked-checking APY boost. Do not promise one. Credit-card bonuses do not apply when the customer has no active eligible credit card.

If these facts lead to a different choice, use the customer’s confirmed full official class name and re-check all opening eligibility.

## Execution order for a checking replacement plus savings opening

1. Complete identity, authority, ownership, and eligibility checks. Confirm the old account has no pending transactions and can pay any early fee.
2. Confirm the replacement checking class and savings class exactly. Confirm the customer understands the fees, rates, funding requirements, and closure consequence.
3. If account limits permit, call `open_bank_account_4821` for the replacement checking account. Record the returned new account ID and status.
4. While the established qualifying checking account remains active, call `open_bank_account_4821` for the savings account. Record the returned savings account ID and status.
5. Funding:
   - For an authorized internal transfer, confirm both accounts belong to the customer, are `ACTIVE` or `OPEN`, have distinct IDs, and that the source has sufficient available funds. Validate a positive USD amount, then call the transfer tool once and verify posting.
   - For an external deposit, do **not** call the internal transfer tool. State the product’s opening-deposit amount and that the customer has 30 days to fund the new savings account by internal transfer or external deposit or it will be closed. Do not claim the deposit is made.
6. Only after the new accounts are successfully created and the old account remains closure-eligible, call the unlocked closure tool for the old checking account.
7. For Blue Account overdraft protection, instruct the customer to open account settings, select Overdraft Protection, select the new savings account as funding source, review and accept the $12.50 per-transfer disclosure, and enable it. This is a customer self-service step.
8. Report successful account identifiers/details returned by tools, the external-funding deadline or verified transfer status, the closure result, and the outstanding self-service overdraft-protection step.

## Failure handling

- **Missing identity, authority, account ownership, product confirmation, or eligibility evidence:** do not perform banking actions; ask for the missing item.
- **Checking-account cap or savings-account cap reached:** do not open the account; explain the applicable maximum.
- **No active checking held for 14 days:** do not open savings; state when the customer becomes eligible if the date is known.
- **Collections or negative balance:** do not open savings until resolved.
- **Closed-for-cause history cannot be confirmed:** do not open checking until it is confirmed.
- **Closure fee cannot be covered, pending transaction exists, notice is incomplete, or status is not open:** leave the account open and explain the blocking condition.
- **Internal transfer fails:** do not retry blindly. Re-read balances/statuses, correct the cause, and obtain confirmation for any changed amount or source.
- **External funding:** never imply an external deposit was received merely because an account was opened.

## Script input and output schema

`scripts/assess_account_change.py` reads one JSON object from stdin and writes one JSON object to stdout.

Required input fields: `today`, `identity_verified`, `authority_confirmed`, `date_of_birth`, `accounts`. For checking-opening eligibility, include `closed_for_cause_last_6_months` as `true` or `false`; omission deliberately produces an evidence failure. Each account should include `account_id`, `account_type`, `account_class`, `status`, `balance`, and `date_opened`. Include `pending_transactions` for a closure target. Set `personal: false` only when a record is known not to be a personal account. Supply `closure_account_id` to assess closure and `notice_satisfied` where notice is nonzero.

Output contains `errors`, account counts, and three objects: `checking_open`, `savings_open`, and `closure`. Each contains an `eligible` boolean and human-readable `reasons`. An account action is valid only if its applicable object is eligible and the live tool state agrees.
