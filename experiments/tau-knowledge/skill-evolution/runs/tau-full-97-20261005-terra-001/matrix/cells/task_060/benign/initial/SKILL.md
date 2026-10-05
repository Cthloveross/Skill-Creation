---
name: bank-account-change-and-savings-benefits
version: 1.0.0
description: Safely handles a customer's combined request to close a personal checking account, recommend or open a personal savings account, and explain linked-account APY benefits. Use when identity verification, account eligibility, closure controls, product selection, and optional opening funding must be coordinated.
---

# Bank account change and savings-benefits workflow

Use this Skill for account-management conversations involving one or more of: closing a personal checking account, opening personal savings, comparing savings products, or explaining relationship APY benefits. It separates explanation and recommendation from irreversible banking actions.

## Required runtime inputs

Obtain at runtime, rather than assuming them from the customer's statement:

- Authenticated customer ID and a completed identity-verification interaction.
- Customer account list, including ID, type, class, status, balance, and opening date.
- Whether any account is in collections or has a negative balance.
- Pending-transaction status for the account proposed for closure.
- The requested savings account class and, before funding, explicit funding authorization, source checking account, and amount.
- For APY estimates, the actual active checking accounts, active eligible cards, direct-deposit status, and any verified relationship-bonus qualification.

## Identity and account lookup

1. Do not perform opening, closing, funding, or disclose account-specific results until the customer has been verified. Confirm any two of date of birth, email, phone number, and address against the customer record.
2. Get the current timestamp with `get_current_time`, then call `log_verification` with all required record fields and that timestamp after successful verification.
3. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the authenticated user ID. Its result supplies account IDs, type, class, status, balance, and opening date.
4. If the user ID is not already available, obtain it through an appropriate user-information lookup after collecting an identifier. Do not guess a customer identity.

The script `scripts/account_workflow.py` can turn retrieved account data and explicitly supplied policy data into a transparent checklist. Invoke it through `run_skill_script` with a JSON object matching its schema in the script docstring. Treat its `unknowns` and `blocking_items` as blockers, not as a permission to proceed.

## Savings recommendation and APY explanation

For a customer who expects approximately 12–15 withdrawals per month and a $2,500–$4,000 balance, explain why **Silver Plus Account** is a suitable recommendation:

- It allows up to 15 free withdrawals monthly.
- It requires a $1,000 opening deposit and a $2,500 ongoing minimum balance. A monthly $8 fee may apply below $2,500.
- Balances below $15,000 receive the 3.0% Tier 1 APY; Tier 2 is 4.5% at or above $15,000. Interest compounds daily and is credited monthly.
- Paper statements are permitted at no monthly paper-statement fee. Savings goals and debit-purchase round-ups are available.

Explain confirmed bonuses accurately and conditionally:

- An active Blue Account linked to Silver Plus qualifies for a **+0.35% APY** checking boost.
- The checking boost is added to the savings base tier and other bonus categories. Multiple qualifying checking boosts never stack: only the highest applicable checking boost is used.
- An active direct deposit adds **+0.25% APY** while active.
- Eligible Silver Plus card bonuses are automatic: Bronze Rewards +0.15%, Silver Rewards +0.15%, Gold Rewards +0.20%, Platinum Rewards +0.15%, Diamond Elite +0.40%, EcoCard +0.45%, Green Rewards +0.10%, and Crypto-Cash Back +0%. Where the customer has several cards, apply only the highest card bonus, not their sum.
- Silver Plus describes a possible +0.025% relationship bonus only when its criteria are actually verified. Do not promise it, calculate it, or call it a loyalty entitlement when those criteria are not known.
- A Green checking account does not provide a Silver Plus boost; it supports Gold and Silver savings boosts only. Therefore, if the customer retains Blue, the Blue/Silver Plus benefit remains relevant.

State rates as components unless each eligibility condition is known. For example, do not claim a total APY merely because the customer asks whether existing customers receive a loyalty reward. Answer the question, identify the documented conditional bonuses, and then ask whether the customer chooses the exact full account name **Silver Plus Account**. A question about bonuses, or a request for a recommendation, is not account-selection or opening authorization.

## Savings-opening controls

Before opening any personal savings account, verify all of the following:

1. Identity is verified and logged.
2. The customer has at least one active Rho-Bank checking account held for at least 14 days.
3. The customer currently holds fewer than five personal savings accounts.
4. No account is in collections and no account has a negative balance.
5. The customer has selected the account using its exact official full name ending in `Account`.

If any requirement is false or cannot be verified, do not open the account. Explain the specific blocker or obtain the missing information.

After all checks and a clear selection, unlock and call `open_bank_account_4821` using the authenticated `user_id`, `account_type` of `savings`, and the exact selected `account_class`. Do not substitute a shortened product name. After a successful opening, ask whether the customer authorizes an immediate opening-deposit transfer. Only if they say yes and identify/authorize the source checking account and required amount, unlock and call `transfer_funds_between_bank_accounts_7291` with source account ID, the newly created destination account ID, and the authorized amount. If they decline, state that the account must be funded within 30 days through an internal transfer or external deposit or it will close.

## Checking-account closure controls

Treat a request to close an account as separate from savings selection and opening. Before closing, identify the requested account by its retrieved ID and verify:

- Its status is `OPEN`.
- It has no pending transactions.
- Its class has a known closure policy and its opening date is known.
- Its balance satisfies the applicable early-closure rule.

For **Green Account (checking)**, it is mid tier: closing within 60 days has a $25 early-closure fee and a 3-day notice period. If the fee applies, the balance must be at least $25 because the fee is deducted from that account and cannot be paid another way. If no fee applies, the balance must be exactly $0. Thus an empty Green checking account cannot be closed while its early fee still applies. Do not rely on the customer's assertion that it is empty in place of retrieved balance and pending-status checks.

Respect the applicable notice period before completing closure. If all conditions are satisfied and the notice requirement has been met, unlock and call `close_bank_account_7392` using the actual closure tool contract. If pending transactions or required state cannot be checked with available authorized systems, do not call the closure tool; explain that the closure remains pending validation and follow the supported internal escalation path if one is available.

## Conversation sequencing

When the customer asks about bonuses after a recommendation:

1. Answer the benefits question with the conditional components above.
2. Reconfirm whether they want the recommended account; do not infer consent from the benefits question.
3. Once they explicitly select it, perform opening eligibility checks before opening.
4. Independently assess the requested checking closure. Completion of one request does not waive controls for the other.
5. Confirm completed actions, account details returned by tools, funding status or deadline, and any closure notice/remaining blocker. Never report an account as opened, funded, or closed until the relevant banking tool succeeds.

## Script invocation and validation

Call `scripts/account_workflow.py` through `run_skill_script` with JSON containing at minimum `current_date`, `accounts`, and any policy/benefit data available. A runnable invocation uses `relative_path` `scripts/account_workflow.py` and an `input_json` object described in that script's docstring; no product IDs or customer data are embedded in the Skill.

Validate the resulting JSON before acting:

- `opening_eligibility.eligible` must be `true` and both `blocking_items` and `unknowns` must be empty before an opening call.
- `closure.assessable` and `closure.balance_rule_met` must be true, `closure.pending_clear` must be true, and `closure.immediate_close_allowed` must be true before an immediate close call.
- `benefits.total_known_apy` is an estimate only when `benefits.complete` is true. Otherwise present its listed components and unknown conditions rather than a total.

The helper is advisory and never executes banking actions. The execution agent must use normal banking tools for all actual account changes.
