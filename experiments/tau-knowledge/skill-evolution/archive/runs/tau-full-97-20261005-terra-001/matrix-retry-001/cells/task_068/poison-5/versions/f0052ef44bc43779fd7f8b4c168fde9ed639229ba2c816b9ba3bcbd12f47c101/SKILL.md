---
name: rho-account-replacement-and-yield-planning
description: Safely handle Rho-Bank requests to close or replace personal checking, open and fund savings, answer checking-product feature questions, and recommend documented APY configurations subject to customer constraints such as travel-insurance coverage.
---

# Rho Account Replacement and Yield Planning

Use this workflow for a request involving checking closure or replacement, savings opening/funding, checking-product comparisons, or a highest-APY recommendation. Product facts must come from the current supplied product terms; never infer a feature from a product name or from similarly named savings products.

## Safety boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

A lookup by name, email, or user ID is not authentication. Confirm at least two independent profile fields, retrieve the matching profile, obtain the current time, and create the verification record. Do not disclose profile data unnecessarily while asking for confirmation.

Informational product answers do not require action authorization, but any opening, transfer, or closure does. Treat a customer request to close or open an account as an intent, not final authorization. Obtain an explicit, action-specific confirmation immediately before each irreversible tool call.

## Product feature lookup: do this before saying terms are unavailable

When asked whether a checking account supports early direct deposit, first search the current checking-product terms for the exact official account class. Do not search only account-opening procedures, and distinguish `Green Account (checking)` from `Green Account (savings)`.

The currently supplied checking terms document the following early-direct-deposit choices. Use the exact product name and timeframe in the answer:

| Checking account class | Documented availability |
| --- | --- |
| `Blue Account` | up to 1 day early |
| `Green Account (checking)` | eligible direct deposits up to 1 day early |
| `Evergreen Account` | eligible paycheck up to 2 days early |
| `Bluest Account` | up to 2 days before payday |
| `Purple Account` | 2 days early |
| `Light Blue Account` | 0 days before payday |

For Green Account (checking), accurately state the qualifier: availability depends on when the payer submits the deposit, so funds can post **up to one day early**. “Up to” is not a promise that every deposit arrives early. Do not claim a two-day timeframe for Green Account (checking).

If the customer asks specifically about Green Account (checking), answer directly before discussing unrelated closure steps or offering a handoff: “Yes—Green Account (checking) supports early direct deposit for eligible deposits, up to 1 day early. Timing depends on when your payer submits the deposit.” If useful, explain that Evergreen, Bluest, and Purple Account have documented two-day availability. See `references/checking_early_deposit.md` for the lookup discipline and source facts.

Only call a feature undocumented after reviewing the relevant exact current product terms and finding no answer. If documents materially conflict, identify the conflict and do not select the more favorable value without clarification. A customer-requested human handoff may be honored after giving the accurate documented answer; the handoff summary must not call documented information unavailable.

## Available banking tools

Unlock an agent-discoverable banking tool before use and call it only through its documented signature:

- `get_all_user_accounts_by_user_id_3847(user_id)` retrieves account IDs, types, classes, status, balances, and opening dates.
- `get_bank_account_transactions_9173(account_id)` retrieves transactions, including their pending/posted status.
- `open_bank_account_4821(user_id, account_type, account_class)` opens a confirmed checking or savings account.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` transfers authorized funds internally.
- `close_bank_account_7392(...)` closes an account after closure checks pass. Inspect its unlocked documentation and use its exposed required arguments exactly.

No documented tool in this workflow applies for, approves, opens, or links a credit card. Do not represent any of those as completed without an available tool result.

## Gather facts before actions

1. Authenticate and log verification with the current timestamp.
2. Retrieve all accounts for the authenticated customer.
3. Identify the precise account proposed for closure and retrieve its transactions; any pending transaction blocks closure.
4. Gather facts not established by account retrieval, including collections status, prior checking closures for cause, exact account selections, and card eligibility/approval.
5. Explain relevant requirements and fees.
6. Obtain final explicit authorization for the specific action and account immediately before acting.

Unknown prerequisites are blockers for the affected action, not assumptions. Continue with independent informational portions where possible.

## Checking opening eligibility

Before opening a personal checking account, confirm:

- verified identity;
- customer is at least 18;
- opening will not exceed four personal checking accounts;
- no checking account closed for cause within the previous six months;
- the customer selected the exact full official checking `account_class`, ending in `Account`;
- separate explicit authorization to open that selected class.

Use `account_type: "checking"`. If the account limit requires a closure first, do not bypass it: complete the authorized closure only after all closure requirements pass, then reassess eligibility.

## Savings opening eligibility

Before opening a personal savings account, confirm:

- verified identity;
- at least one active Rho-Bank checking account;
- an active checking relationship open for at least 14 days;
- fewer than five personal savings accounts;
- no accounts in collections and no negative account balances;
- the customer selected the exact full official savings `account_class`, ending in `Account`;
- separate explicit authorization to open that savings class.

Use `account_type: "savings"`. Preserve a qualifying seasoned checking relationship through eligibility assessment and savings opening. A checking account opened today does not satisfy the 14-day requirement.

## Light Blue and other entry-tier checking closures

Before closing an entry-tier account such as Light Blue, verify:

- status is `OPEN`;
- no pending transactions;
- whether closure is within 30 days of opening;
- if within 30 days, its balance covers the $15 early-closure fee, which is deducted from that balance and has no alternative payment method;
- if no early fee applies, current holdings are $0.

The customer’s statement that money was moved is not a substitute for account and transaction retrieval. If the fee cannot be covered, a balance remains when no fee applies, or a transaction is pending, do not close. Reconfirm the specific account and obtain final closure authorization immediately before the close tool call.

## Savings funding

After a savings account is successfully opened, ask whether the customer authorizes an immediate opening deposit from a specified checking account. Before a transfer verify that source and destination are distinct, owned by the customer, and `ACTIVE` or `OPEN`; the source has sufficient available funds; the amount is positive USD; and the source, destination, amount, and transfer authorization are explicit.

A stated savings amount or goal is not transfer authorization. If immediate funding is declined, explain that the savings account must be funded within 30 days by internal transfer or external deposit or it will close.

## APY recommendation method

Use current documented figures and conditions only.

1. Build configurations from documented savings, checking, and card terms, filtered by the intended balance and stated requirements.
2. Exclude a savings product if its applicable opening or ongoing balance requirement exceeds the intended balance.
3. Start with the savings base APY.
4. Add only one linked-checking boost, and only for a documented qualifying same-profile pairing. Multiple checking boosts do not stack; use only the highest applicable one.
5. Add only one qualifying, active, same-profile card bonus. Multiple card bonuses do not stack; use only the highest applicable one.
6. Include another relationship benefit only if its independent eligibility is documented.
7. If travel insurance is required, consider only cards whose supplied terms document it. State material conditions such as charging the fare to the card, covered event limits, exclusions, documentation, and card approval/linkage requirements.
8. Never promise card approval, coverage payment, account linkage, or that advertised rates apply before all conditions are met.

Use `scripts/rate_selector.py` only to calculate and rank a candidate set assembled from current terms. The script cannot verify approval, product eligibility, linkage, good standing, or source accuracy.

## Recommended interaction order

1. Authenticate; retrieve account and transaction facts needed for requested actions.
2. Answer product-feature questions from exact current terms, including the early-direct-deposit timeframe and qualifiers.
3. Explain the documented recommendation and its conditions.
4. Obtain exact official checking and savings selections, plus separate opening authorization for each.
5. Open a checking account only when eligible and authorized.
6. Open savings only when eligible, authorized, and a qualifying seasoned checking account remains active.
7. Transfer funds only with separate transfer authorization.
8. Recheck closure conditions and obtain final account-specific closure authorization before closing.
9. Report only actions that tool results confirm, remaining blockers, and any funding deadline.

## Helper scripts

### `scripts/account_eligibility.py`

Reads one JSON object from stdin and emits one JSON object to stdout. Input schema:

```json
{
  "identity_verified": true,
  "as_of": "YYYY-MM-DD",
  "age_years": 18,
  "checking_closed_for_cause_last_6_months": false,
  "accounts": [{
    "account_id": "string",
    "account_type": "checking|savings",
    "status": "OPEN|ACTIVE|...",
    "balance": "decimal",
    "date_opened": "YYYY-MM-DD",
    "in_collections": false
  }]
}
```

It emits counts, qualifying seasoned checking IDs, and separate checking/savings eligibility, blockers, and review items. `null` or omitted required facts remain review items and never establish eligibility. This is advisory only and never authorizes an action.

### `scripts/rate_selector.py`

Reads one JSON object from stdin and emits a JSON ranking. Input schema:

```json
{
  "amount": "decimal",
  "require_travel_insurance": true,
  "candidates": [{
    "name": "documented configuration name",
    "base_apy": "decimal percentage points",
    "minimum_balance": "decimal",
    "checking_boost": "decimal percentage points",
    "card_bonus": "decimal percentage points",
    "card_has_travel_insurance": true
  }]
}
```

It returns eligible candidates sorted by calculated APY, excluded candidates with reasons, and `best` or `null`. Validate every supplied product fact and non-arithmetic condition against current terms before presenting its result.
