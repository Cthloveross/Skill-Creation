---
name: checking-replacement-and-savings-opening
summary: Safely replace a personal checking account and open a high-yield personal savings account while enforcing identity, closure, eligibility, funding, and consent requirements.
description: Use for a customer who wants to close or replace a personal checking account and/or open personal savings. It verifies account facts through the documented banking tools, applies checking closure fees and savings eligibility rules, recommends products from supplied product facts, and performs only customer-authorized bank actions.
---

# Checking replacement and savings opening

## Scope and safety rules

Use this Skill for personal checking closure, opening a replacement personal checking account, and opening a personal savings account. Treat account status, balance, dates, transaction status, verification status, account counts, and adverse-history conditions as system facts: never infer them from a customer's estimate.

Do not close an account, open an account, or transfer funds until the relevant prerequisites and customer authorization are established. The customer does not call internal tools; the agent uses the documented banking tools.

If a required tool or required system fact is unavailable, explain the precise blocker. For an unresolved closure request that requires agent handling, transfer using `account_closure_request`; otherwise do not claim completion or invent a result.

## Required authentication and account lookup

1. Identify the customer through a supported lookup.
2. Complete identity verification before account actions. Obtain confirmation of two of the four identity fields (date of birth, email, phone number, address) without unnecessarily exposing values retrieved from the system. Then call `log_verification` with the complete retrieved customer record and the current timestamp.
3. Obtain the current timestamp with `get_current_time` for the verification audit record.
4. Unlock and use `get_all_user_accounts_by_user_id_3847` to retrieve all accounts. Use its returned account IDs, types, classes, statuses, balances, and opening dates; do not use an account identifier supplied only in conversation.
5. For every account proposed for closure, unlock and use `get_bank_account_transactions_9173`. A transaction whose status is `pending` blocks closure.

The available account lookup is also the source for counting existing checking and savings accounts and for checking balances, status, and tenure. A current-account lookup alone may not establish a closed-for-cause history, collections status, or profile verification status. Obtain those required facts from an appropriate supported system record or do not proceed with the affected opening.

## Evaluate a checking-account closure

Only close a personal checking account after all of these are true:

- Its status is `OPEN`.
- It has no pending transactions.
- Its current balance is zero if no early-closure fee applies.
- If an early-closure fee applies, its current account balance is at least the fee. The fee is deducted from that account; it cannot be paid by another method.

Determine elapsed calendar days from the returned opening date to the current date. Apply these requirements by the account's exact official class:

| Tier / checking classes | Early fee and period | Notice |
|---|---:|---:|
| Entry: Light Blue Account, Light Green Account, Green Fee-Free Account | $15 when under 30 days | 0 days |
| Mid: Blue Account, Green Account (checking) | $25 when under 60 days | 3 days |
| Premium: Evergreen Account | $50 when under 90 days | 7 days |
| Elite: Bluest Account | $100 when under 180 days | 14 days |

Do not substitute a monthly fee or another product fee for this fee. If the balance cannot cover an applicable early fee, do not close the account. Explain that the account needs enough balance for the fee and obtain authorization before any customer-funded transfer or deposit intended to cure that blocker. Follow the actual unlocked `close_bank_account_7392` schema after all conditions, notice requirements, and authorization are satisfied.

## Evaluate and open the replacement checking account

Before opening personal checking, verify all of the following from system records:

- The customer is verified and is at least 18 years old.
- Opening the account will not cause the customer to exceed four personal checking accounts.
- No checking account was closed for cause in the preceding six months.
- The customer selected the exact full official `account_class` name ending in `Account`.

Recommend a class only from documented product facts that match the customer's stated priorities. Explicitly disclose relevant tradeoffs such as early-direct-deposit timing, balance requirements, and fees. A recommendation is not account-opening consent: ask the customer to confirm the exact class before acting.

For a customer whose stated priority is access to direct deposits one or two days early, Evergreen Account is a documented option with access up to two days early. Confirm that the customer wants Evergreen Account (or another exact selected class) before opening. Use `open_bank_account_4821` with the authenticated `user_id`, `account_type: "checking"`, and exact selected class.

## Evaluate and open the savings account

Before opening a personal savings account, verify:

- The customer is verified.
- At least one active Rho-Bank checking account exists and has been held for at least 14 days.
- The customer currently has fewer than five personal savings accounts.
- No account is in collections and no account has a negative balance.
- The customer confirms the exact official savings `account_class` ending in `Account`.

Preserve a qualifying established checking account until the savings eligibility check is complete. This matters in a replacement workflow: closing the old checking account before opening savings can eliminate the only qualifying checking relationship or leave only a checking account that is less than 14 days old.

When comparing savings products for a stated deposit amount, rank only products whose documented opening minimum **and** ongoing minimum needed to maintain the advertised benefits can both be met by the planned maintained balance. State separately any available credit-card or linked-checking bonuses and do not assume them apply. Where the customer holds no qualifying cards or checking/savings pair, recommend based on the base rate that actually applies.

After the class is confirmed, use `open_bank_account_4821` with `account_type: "savings"` and the exact official class. Then ask whether the customer authorizes an immediate internal transfer and identify both the source checking account and amount. Use `transfer_funds_between_bank_accounts_7291` only after that authorization and after checking available funds. If the customer declines or the funds are external, tell them they have 30 days to fund the new savings account through an internal transfer or external deposit or it will be closed.

## Recommended execution order for a replacement plus savings request

1. Verify identity and retrieve all accounts and the old checking account's transactions.
2. Verify all checking-opening and savings-opening prerequisites, including the old checking account's tenure and closure facts.
3. Present the matching checking recommendation and savings comparison; get confirmation of each exact class and any transfer authorization.
4. Open the replacement checking account after its opening checks pass.
5. While a qualifying checking account remains active, open the savings account after its checks pass and arrange/describe funding.
6. Re-check the old checking account immediately before closure. Apply its fee and notice rule, then close it only if eligible and authorized.
7. Report account-opening results, funding status or deadline, closure outcome or exact blocker, and any required follow-up. Do not describe an attempted action as completed unless the tool returned success.

## Optional deterministic helper

`scripts/assess_bank_workflow.py` evaluates supplied account, transaction, and product facts without making bank actions. It reads one JSON object from stdin and emits one JSON assessment to stdout.

Input schema:

- `now` (required): ISO date/time or `MM/DD/YYYY` date.
- `closure` (optional): `{ "account": {"account_class", "status", "balance", "date_opened"}, "transactions": [{"status": ...}] }`.
- `checking_opening` (optional): `{ "verified", "age_years", "existing_checking_count", "closed_for_cause_past_6_months", "account_class_confirmed" }`.
- `savings_opening` (optional): `{ "verified", "active_checking_tenure_days", "existing_savings_count", "has_collections", "has_negative_balance", "account_class_confirmed" }`.
- `savings_candidates` (optional): a list of `{ "account_class", "apy_pct", "opening_min", "ongoing_min" }` plus `planned_savings_balance`.

The helper emits `closure`, `checking_opening`, `savings_opening`, and `savings_ranking` results, each with explicit blockers. Treat an `unknown` result as a requirement to retrieve the missing system fact, not as approval. Validate that eligible closure has no blockers, each selected opening assessment is eligible, and a recommended savings candidate fits both stated balance thresholds before performing any bank action.
