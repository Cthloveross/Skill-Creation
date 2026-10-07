---
name: personal-checking-transition
version: 1.0.0
description: Safely verifies, closes a personal checking account, opens a replacement checking account, and supports evidence-based savings/APY recommendations. Use when a verified customer wants to replace or close a checking account, including a transition that may later include savings or credit-card products.
---

# Personal Checking Transition

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow for personal checking closure, replacement checking opening, and a separately authorized later savings/APY review. Do not treat a request to close an old account as authorization to open, fund, transfer, or apply for another product. Do not claim a card application is approved, a rate is guaranteed, or an account can be closed until the relevant live checks and confirmations are complete.

Use the execution agent's normal banking tools for all reads and writes. Packaged scripts only assess supplied data; they never perform banking actions.

## Required live verification before any banking action

1. Locate the customer with a supplied name or email and retrieve their profile.
2. Verify identity by asking the customer to confirm **two of four** profile fields: date of birth, email, phone number, or address. Do not reveal unconfirmed fields as prompts that allow blind confirmation.
3. Record the successful verification with `log_verification`, using a fresh `get_current_time` result.
4. Confirm the customer is the account owner and has authority to close/open accounts and transfer money if a transfer is requested.
5. Obtain explicit confirmation of each consequential action immediately before it occurs. Separate confirmations are needed for account closure, opening a named replacement, transfers/funding, and any credit-card application.

If identity, ownership, authority, or confirmation cannot be established, stop without performing a banking action and explain the missing prerequisite.

## Account discovery and closure checks

After identity verification, unlock and use the documented tools in this order as applicable:

1. `get_all_user_accounts_by_user_id_3847(user_id)` to find the target account and all customer accounts. Confirm the target is a personal checking account, belongs to the verified user, and obtain `account_id`, `account_class`, `status`, balance/current holdings, and `date_opened`.
2. `get_bank_account_transactions_9173(account_id)` to determine whether **any** transaction is `pending`.
3. `get_debit_cards_by_account_id_7823(account_id)` to identify every associated debit card.
4. Evaluate account closure with `scripts/closure_plan.py`. Supply the live date, account facts, transaction result, and whether all associated cards have already been closed.

### Required checking-account closure conditions

All of these must be satisfied before calling `close_bank_account_7392`:

- The account status is `OPEN`.
- There are no pending account transactions.
- Associated debit cards have been closed first.
- For an early closure within the class's window, the balance is at least the fee; the fee is deducted from that balance and cannot be paid another way.
- If no early closure fee applies, the account balance is exactly $0.
- Any applicable notice period has elapsed after a recorded closure request.

Closure tiers are:

| Account class | Early closure rule | Notice |
|---|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | $15 if closed within 30 days | 0 days |
| Blue Account, Green Account (checking) | $25 if closed within 60 days | 3 days |
| Evergreen Account | $50 if closed within 90 days | 7 days |
| Bluest Account | $100 if closed within 180 days | 14 days |

Do not infer that “moved my money out” proves the balance is zero, that no transactions are pending, or that the account is outside the early-fee window. Obtain the live account and transaction results.

### Debit-card dependency

A checking account cannot be closed while an associated debit card remains open. For each non-closed associated card, apply the debit-card closure procedure before the checking closure:

- Verify it belongs to the user and is `ACTIVE` or `PENDING`.
- Obtain the customer's selected reason (`lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`).
- Verify no pending/processing card transactions and no pending refunds. For ordinary reasons, verify it has been active at least 14 days; lost, stolen, and fraud-suspected reasons bypass only the age requirement.
- Use `close_debit_card_4721(card_id, reason)` only after those conditions are met.

If a card is in an unsupported status, has unresolved pending activity/refunds, or the available data cannot establish a card prerequisite, do not close the checking account. Explain the specific blocker rather than guessing.

Once every condition is confirmed and any required notice has elapsed, unlock and call `close_bank_account_7392` using the tool's exposed required arguments. Confirm the returned closure result to the customer. If a closure tool does not expose a scheduling/notice parameter, do not invent one; wait until the notice is complete before calling it.

## Opening the replacement checking account

Only begin after the customer explicitly selects a replacement account class and authorizes opening it. A customer may choose to close first and defer all replacement or savings steps.

Before `open_bank_account_4821`:

1. Confirm verified identity and customer authority.
2. Confirm age is at least 18 from the profile.
3. Using the account lookup, count personal checking accounts and ensure the customer will not exceed four.
4. Determine whether the customer has a checking account closed for cause in the prior six months. If the available account lookup cannot establish this, obtain the required record through approved procedures; do not assume eligibility.
5. Confirm the exact official `account_class` string ending in `Account` and disclose material minimum-balance/fee requirements supported by the product documentation.
6. Call `open_bank_account_4821` with the verified `user_id`, `account_type: "checking"`, and exact selected `account_class`.

Do not recommend a premium account solely from benefits if its opening or ongoing balance requirements are unaffordable. A fee-waiver balance is different from an account-opening eligibility rule; disclose both where documented.

## Later savings and APY recommendation

Treat savings work as a new, separately confirmed phase. Before opening savings, verify an active checking account, fewer than five personal savings accounts, no accounts in collections or with negative balances, and at least 14 days of checking tenure. Confirm the exact savings class, opening-deposit source, amount, and funding authorization.

When comparing APY, use only product terms present in approved documentation and current eligibility facts:

1. Exclude products whose opening or ongoing balance requirements the customer cannot meet.
2. Start with the savings account base APY applicable to the proposed balance.
3. Consider only documented checking-savings pairings. If several checking boosts apply, select only the highest; checking boosts do not stack with each other.
4. Consider only active/approved eligible credit cards. If several card bonuses apply, select only the highest; card bonuses do not stack with each other.
5. Add independently documented bonuses only when their qualification is demonstrated. Do not treat a proposed or pending card application as an active bonus.
6. Disclose associated account fees, required balances, credit-score/subscription requirements, and uncertainty before recommending a combination.

Use `scripts/apy_comparison.py` to calculate a transparent rate from evidence-backed candidate bonuses. The executor must provide the product facts at runtime; do not hardcode customer IDs, balances, account selections, or assumed approvals into scripts.

## Handling incomplete information

If the customer cannot provide an opening date or pending-transaction status, retrieve them through the account and transaction tools. If tools or records cannot provide a required condition, state that closure/opening cannot proceed yet and identify what must be verified. Do not transfer a balance merely to make closure eligible without specific transfer authorization and verification of source/destination status, ownership, and funds.

## Script usage

### Closure assessment

```sh
python3 scripts/closure_plan.py <<'JSON'
{"account_class":"Light Blue Account","status":"OPEN","balance":"0.00","date_opened":"2025-09-01","current_date":"2025-11-14","pending_transaction_count":0,"all_associated_cards_closed":true,"notice_request_date":"2025-11-14"}
JSON
```

The script accepts JSON on stdin and emits JSON on stdout. It returns the tier, fee determination, notice completion date, explicit blockers, and `can_invoke_close_tool`. Validate that `blockers` is empty and `can_invoke_close_tool` is true before using the account-closure tool. Its assessment does not replace live identity, ownership, or debit-card checks.

### APY comparison

```sh
python3 scripts/apy_comparison.py <<'JSON'
{"base_apy":"5.50","checking_boosts":[{"name":"Eligible checking pairing","apy":"0.75","eligible":true}],"card_bonuses":[{"name":"Active eligible card","apy":"0.60","eligible":true}],"other_bonuses":[{"name":"Verified relationship bonus","apy":"0.00","eligible":true}]}
JSON
```

The output reports the selected highest checking/card bonuses, total APY, and excluded candidates. Validate each input against product documentation and live eligibility before presenting the output to a customer.
