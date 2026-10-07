---
name: personal-account-transition
version: 1.1.0
description: Safely advise and complete a personal checking replacement, checking closure, and personal savings opening, including identity authentication, live eligibility checks, product/rate comparison, funding, and sequencing. Use for a customer who wants to upgrade/close checking and/or maximize savings APY.
---

# Personal Account Transition

Use normal bank tools directly for bank actions; never give internal tool names or parameters to the customer. Do not state an action, funding, card approval, rate bonus, or closure as completed unless the relevant system result says so.

## Required evidence and authentication

1. Identify the customer from an identifier they provide. A name or a record lookup does **not** authenticate them.
2. Ask them, without revealing profile values, to confirm two of email, phone number, date of birth, or address. Compare both against the retrieved profile exactly.
3. After both match, get the current time and log verification with the full profile and timestamp. No account action may precede this.
4. Retrieve all live bank accounts before giving a definitive eligibility decision, funding recommendation, or closure action. When calculating a card-dependent APY, retrieve the customer's credit-card accounts with `get_credit_card_accounts_by_user(user_id)` as well; do not infer card ownership from an application, statement, or customer intention.
5. Use authoritative account information for account ID, type/class, status, exact balance, and opening date. Do not treat “empty” as $0 or assume a customer’s account has no pending items. Customer answers may establish customer-specific history (such as prior closure for cause) when no authoritative source exists, but unknown facts remain blockers.

Unlock an internal agent tool only when its documented procedure applies, then call it directly. Relevant tools are:

- `get_all_user_accounts_by_user_id_3847(user_id)` for checking/savings account facts;
- `get_credit_card_accounts_by_user(user_id)` for current card holdings used in APY comparison;
- `open_bank_account_4821(user_id, account_type, account_class)` after eligibility and exact selection;
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` for an authorized internal opening deposit; and
- `close_bank_account_7392(account_id, reason, waive_early_closure_fee)` only after closure prerequisites pass. Never waive a fee unless a documented, authorized waiver is available.

## Separate eligibility decisions

Do not combine these gates or let one newly opened product satisfy another product's prerequisites.

### Personal checking opening

Before opening, confirm: identity is verified; age is at least 18; the customer will not exceed the limit of four personal checking accounts; no checking account was closed for cause in the past six months; and the customer has selected an exact official checking `account_class` as documented for that product (including any parenthetical qualifier).

### Personal savings opening

Before opening, confirm: identity is verified; there is an ACTIVE or OPEN Rho-Bank checking account held at least 14 days; fewer than five personal savings accounts; no account has a negative balance or is in collections; and the customer has selected an exact official savings `account_class` as documented for that product (including any parenthetical qualifier).

A checking account opened today cannot satisfy the 14-day savings rule. If the old checking is the only seasoned qualifying account, keep it open until the savings opening succeeds. Do not close the only qualifying checking first merely because the customer calls it a replacement.

Use `scripts/assess_account_workflow.py` with normalized live facts as an advisory checklist. A `fail` or `unknown` result is not permission to proceed. The helper does not prove pending-transaction or collections information if those fields were absent from the source response.

## Product/rate advice

First determine whether the customer is asking for the highest **headline** APY, the highest rate they can sustain at their stated balance, or lowest net cost. Explain the distinction. Evaluate the opening deposit and continuing minimum separately: qualifying to open is not enough to keep a tier's rate/benefits.

For the documented premium products, the important balance facts are:

| Savings class | Base APY | Opening minimum | Ongoing minimum |
|---|---:|---:|---:|
| Gold Account | 5.5% | $5,000 | $10,000 |
| Gold Plus Account | 6.0% | $10,000 | $25,000 |
| Platinum Account | 6.5% | $25,000 | $50,000 |
| Platinum Plus Account | 7.0% | $50,000 | $100,000 |
| Diamond Elite Account | 7.5% | $100,000 | $250,000 |

Savings APY may be `base + one highest applicable active-card bonus + one highest applicable qualifying-checking boost`. Multiple credit-card bonuses never stack, and multiple checking boosts never stack; a qualifying checking boost and the one card bonus may stack. Do not invent an exact boost merely because a pairing is listed as qualifying. Do not promise a bonus from a card application: it must be an active eligible card under the same profile.

For example, Platinum Plus has daily compounding and monthly interest crediting. Purple checking + Platinum Plus savings has a documented +0.3% checking boost, and an active Diamond Elite Card has a +0.6% Platinum Plus card bonus. Purple has a $15 monthly maintenance fee, waived with a $3,750 minimum daily balance; disclose that cost when recommending the pairing, particularly if the customer intends to leave the checking balance at $0. The highest APY and the highest net return after checking fees are not necessarily the same recommendation.

Run `scripts/compare_savings_rates.py` for a reproducible comparison from stated balance, active checking classes, and active cards. Its output identifies documented numeric alternatives and marks data gaps; it does not determine approval, product eligibility, customer choice, or funding. If a requested card opening/approval process is not documented or available, explain that limitation rather than inventing a workflow or completing the card action.

## Selection, funding, and safe action order

A recommendation is not a product selection. Before each account opening, obtain clear confirmation of the full official account class. Before a transfer, obtain explicit authorization for the amount and source; do not infer transfer permission from a stated external savings balance.

For a coordinated checking replacement and savings opening, after all gates and choices pass:

1. Open the chosen checking account, if requested and eligible.
2. Leave any existing seasoned qualifying checking OPEN and open the chosen savings account.
3. Ask whether the customer wants the required opening deposit transferred now. Transfer only if source and destination are distinct, OPEN/ACTIVE, same-customer accounts; the source has sufficient funds; and the positive USD amount is explicitly authorized.
4. If no immediate internal transfer is made, tell the customer that the savings account must be funded within 30 days by internal transfer or external deposit or it will close. State the required opening minimum and any higher ongoing balance they need for their stated rate.
5. Immediately before a requested old-checking closure, refresh its live facts and verify status OPEN, its closure tier/window, and the balance rule. Confirm that no transactions are pending whenever the account inquiry exposes pending status or a dedicated pending-status check is available. Then close only if eligible.

For Light Blue, Light Green, and Green Fee-Free checking, the early fee is $15 if closure occurs within 30 days, with no notice period. If the early fee applies, the balance must cover it; otherwise the current balance must be exactly $0. For other tiers, look up their relevant fee/window/notice before action. Do not invent a clear pending status. If the normal account inquiry does not expose it and no separate inquiry is documented, a single requested `close_bank_account_7392` call is the available authoritative closure check once every other prerequisite is established; treat its success or error as authoritative. Do not retry a rejected/UNKNOWN closure without resolving its stated cause, and never retry an UNKNOWN outcome.

## Customer response and exceptions

Report returned account identifiers, statuses, and funding facts separately from planned actions. If a condition is unmet, name the precise condition and next step. Do not transfer routinely for an unmet eligibility condition.

For an explicit closure request that cannot be completed because of a technical/system failure, transfer to a human with `account_closure_request`. Use `technical_system_error` for another workflow-blocking technical failure. For ordinary missing consent or eligibility, explain the requirement rather than escalating.

## Script contracts

Both scripts read one JSON object from stdin and emit one JSON object on stdout. They make no bank changes.

- `scripts/assess_account_workflow.py`: normalized account and eligibility facts in (it also accepts the common account-tool aliases `class`, `level`, and `current_holdings`); pass/fail/unknown eligibility and closure checks out.
- `scripts/compare_savings_rates.py`: `deposit_amount`, `checking_classes`, and `active_credit_cards` in; documented rate candidates, applicable numeric boosts, balance tests, the highest balance-sustainable candidate, and limitations out.
