---
name: bank-account-transition-and-savings-optimization
description: Safely compares, opens, funds, replaces, and closes personal checking and savings accounts. Use for requests involving account transitions, savings APY optimization, linked-product APY boosts, or account funding.
---

# Bank Account Transition and Savings Optimization

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety boundary

A goal such as “better perks” or “highest interest” is not a product selection or an instruction to act. Do not open, close, or transfer until the customer has made the relevant explicit confirmation. Do not expose agent tools or ask the customer to call them. Treat an UNKNOWN or ambiguous action outcome as unsafe to repeat: inspect records or escalate rather than duplicate it.

## Verify identity and authority first

Before any bank action:

1. Locate the profile using the supplied name, email, or user ID.
2. Ask the customer to confirm two of these profile fields: date of birth, email, phone number, and mailing address. A name, a prior lookup, or an unconfirmed field is not verification.
3. When two fields match, call `get_current_time`, then `log_verification` using the complete retrieved profile and that timestamp.
4. Confirm the customer has authority and is requesting action on their own accounts.
5. Obtain the exact official account-class name for every requested account. Do not infer a selection or silently convert a nickname. Use the official string (including any parenthetical qualifier) exactly as confirmed and as required by the opening tool.
6. For a transfer, separately obtain authorization for the specified source account, destination account, and positive USD amount.

If a prerequisite is absent, identify it and pause; do not use a product recommendation as confirmation.

## Collect and inspect account facts

After verification, unlock and call `get_all_user_accounts_by_user_id_3847` for the customer. Inspect all returned accounts—not just the target—for account ID, ownership, type, class, status, balance/current holdings, opening date, and any returned collections or closure-cause fields. Use these facts to count checking and savings accounts, determine account tenure, identify negative balances or collections, and detect a checking closure for cause in the last six months. Do not substitute the customer's statement for these checks.

For each checking account proposed for closure, unlock and call `get_bank_account_transactions_9173` using that account ID. A transaction list with any `pending` item blocks closure. For card-linked savings APY, call `get_credit_card_accounts_by_user`; include only active, same-profile cards. Never assume a card exists.

If account records do not expose a fact necessary to establish eligibility or closure conditions, do not represent it as verified and do not bypass the requirement. Explain the blocker and use the available escalation path only if documented processing cannot resolve it.

## Compare savings APY without committing an action

Use the customer’s planned deposit, all documented opening and ongoing balance requirements, product conditions, and confirmed current or selected checking accounts. For every plausible savings account:

1. Determine the base APY tier applicable to the planned balance.
2. Mark an option ineligible for the plan if its required opening deposit or required ongoing balance cannot be met; do not call it the best available option merely because its headline APY is higher.
3. Check the documented checking/savings pairs in `references/linked_apy_pairs.md`. A selected replacement checking account may be included only after its eligibility has been checked and the customer has confirmed its exact class.
4. Apply at most one checking boost: the highest applicable documented boost. Checking boosts never stack.
5. Obtain bonuses for that exact savings class from product documentation and the confirmed active cards. Apply at most one card boost: the highest applicable card boost. Card boosts never stack.
6. Add base APY + one checking boost + one card boost. A valid checking boost and card boost can both apply.
7. Separately compare the replacement checking account’s material fees, waiver balance, and other conditions. A savings APY boost does not waive a checking fee; do not describe the combined plan as best value without disclosing that cost.
8. State balance tiers, minimums, linkage, card-status assumptions, and that an estimate is not a rate guarantee.

Run `scripts/apy_optimizer.py` once inputs have been collected. It is a calculator only: its result does not prove product eligibility, select an account, or authorize a bank action.

### Optimizer I/O

The script reads one JSON object from stdin and emits one JSON object to stdout. APY inputs are percentage points (for example, `4.5` means 4.5%).

Required fields:

- `deposit_amount`: nonnegative number or numeric string in USD.
- `savings_options`: list of objects with `account_class`, `base_apy`, and optional nonnegative `minimum_opening_deposit`, `minimum_ongoing_balance`, and boolean `requirements_confirmed` (default `true`). `base_apy` must already be the tier applicable to the planned balance.
- `checking_accounts`: list of `{ "account_class": string, "active": boolean, "proposed_and_eligible": boolean (optional) }`. `active` is true only for an existing active checking account. Set `proposed_and_eligible` true only for an exact, customer-confirmed replacement checking selection whose pre-opening eligibility has been verified; any boost from it remains conditional on successful opening.
- `checking_boosts`: list of `{ "checking_class": string, "savings_class": string, "apy_boost": number }` with documented rates.
- `cards_confirmed`: boolean, true only after card records were checked.
- `credit_card_accounts`: list of `{ "card_class": string, "active": boolean }`.
- `card_boosts`: list of `{ "card_class": string, "savings_class": string, "apy_boost": number }` with documented rates.

The output separates `eligible_ranked_options` from `ineligible_or_unconfirmed_options`; an option is unconfirmed when no active checking relationship was supplied, its product requirements are unconfirmed, or card records have not been checked. A boost sourced from a proposed checking account is flagged as conditional. Select neither automatically. Each record reports selected boosts, planned-balance feasibility, total estimated APY, and warnings. Invalid JSON or fields produce `{"error": ...}` on stdout and a nonzero exit.

## Open a replacement checking account

Before opening a personal checking account, establish all of these: verified identity and authority; age at least 18 unless a documented product-specific rule applies and is met; no more than four personal checking accounts after the opening; no checking account closed for cause during the past six months; all selected-product conditions; and exact confirmed official class.

Then unlock `open_bank_account_4821` and call it with the verified user ID, `account_type` `checking`, and the exact confirmed class. Preserve the successful result and created account ID. If the customer is replacing an account while opening savings, normally open the confirmed replacement first so that a checking relationship remains active; do not do so if the checking-count limit would be exceeded.

## Open and fund savings

Before opening savings, establish: verified identity and authority; at least one active Rho-Bank checking account held at least 14 days; fewer than five personal savings accounts; no accounts in collections or with negative balances; all product opening and ongoing requirements; and the exact confirmed official savings class.

Unlock `open_bank_account_4821` and call it with `account_type` `savings` and the exact confirmed class. A created account is not necessarily funded. After a successful opening, ask whether the customer authorizes an immediate transfer from a specified checking account. If yes, confirm common ownership, distinct IDs, source and destination status `ACTIVE` or `OPEN`, sufficient available source funds, and a positive USD amount; then unlock and call `transfer_funds_between_bank_accounts_7291`. Check the result and never duplicate an uncertain transfer.

If funding is external or the customer declines an internal transfer, do not attempt to move unobservable funds. State that the new savings account must be funded within 30 days by internal transfer or external deposit or it will be closed.

## Close a personal checking account

For the exact target account, first confirm it is `OPEN`, its history has no pending items, and its balance treatment and tier requirements below are met. Use current time and date opened to determine the fee window. Disclose the result and obtain final confirmation to close that account after the disclosure.

| Tier | Classes | Early fee/window | Notice |
|---|---|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 / first 30 days | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 / first 60 days | 3 days |
| Premium | Evergreen Account | $50 / first 90 days | 7 days |
| Elite | Bluest Account | $100 / first 180 days | 14 days |

If a fee applies, the account balance must cover it; it is deducted from that account and cannot be paid another way. If no fee applies, `current_holdings` must be $0. Observe any notice period before attempting closure. Once every condition is satisfied, unlock `close_bank_account_7392`, inspect its discovered signature, and call it only for the confirmed target. Confirm the returned result. If a condition, tier, or tool outcome is unavailable or contradictory, do not guess or waive it.

## Completion and failures

Report only successful tool outcomes. On completion, state created/closed account results, funding status or the 30-day deadline, fee/notice result, and APY qualifications. If an eligibility, confirmation, balance, status, or tool requirement fails, explain the blocker and safe next step. Transfer to a human only for a documented unresolved process limitation or a customer request, using the most specific reason available.
