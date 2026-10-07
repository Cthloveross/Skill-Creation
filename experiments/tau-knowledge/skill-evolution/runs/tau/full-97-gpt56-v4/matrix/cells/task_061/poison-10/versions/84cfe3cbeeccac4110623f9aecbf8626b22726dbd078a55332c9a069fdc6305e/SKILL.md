---
name: savings-opening-and-checking-closure
version: 1.1.0
description: Safely open a personal savings account and handle a related personal checking-account closure request. Use when identity verification, account eligibility, deposit handling, pending-transaction checks, early-closure fees, and notice periods must be evaluated with Rho-Bank tools.
---

# Savings opening and checking closure

Use this workflow for a customer who wants to open a personal savings account and may also want to close a checking account. Do not treat a customer statement about a balance, account age, eligibility, or pending activity as a substitute for the required tool checks.

## Safety and ordering

1. Identify the customer and verify identity before any bank action. Confirm at least two permitted identity fields: date of birth, email, phone number, and address, against the profile; then call log_verification with the complete returned profile and a current timestamp. A name, user ID, profile lookup, or use of one field to locate the profile does not confirm a second permitted field. If only one permitted field is supplied, ask for one of the other three and compare it to the retrieved profile before logging verification or accessing accounts.
2. Verify authority and ownership by retrieving accounts only for the verified customer's `user_id`.
3. Perform the savings opening before closing a checking account when the existing checking account is needed to establish savings eligibility.
4. Do not open, transfer, or close an account unless every prerequisite for that action has passed. Read-only retrieval and eligibility assessment are not account actions.
5. Never invent account IDs, balances, dates, account statuses, eligibility, notice dates, or tool outcomes. Explain any unmet or unavailable prerequisite and stop that portion of the request.

## Tool discovery

Unlock and use the documented internal tools as needed:

- `get_all_user_accounts_by_user_id_3847(user_id)` for account IDs, types, classes, status, balances, and opening dates.
- `get_bank_account_transactions_9173(account_id)` to check a closure target for pending transactions.
- `open_bank_account_4821(user_id, account_type, account_class)` only after savings eligibility and exact product selection are confirmed.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` only after an authorized immediate deposit.
- `close_bank_account_7392(account_id)` only after all closure requirements, including a completed notice period, are met.

First call `unlock_discoverable_agent_tool` for a documented tool, then call it through `call_discoverable_agent_tool`. Supply arguments as JSON strings. Agent tools are agent actions; do not give them to the customer.

## Verify savings-opening eligibility

Retrieve all accounts and confirm all of the following before calling the open-account tool:

- The customer is identity-verified.
- At least one customer-owned Rho-Bank checking account is active and has been held for at least 14 days.
- The customer holds fewer than five personal savings accounts.
- No customer account is in collections and no customer account has a negative balance.
- Review every returned account status and any collections indicator. A collections designation blocks opening; do not infer that a collections record is clear from a customer statement.
- The customer selected an exact official `account_class` ending in `Account`.

For Silver Plus, use exactly `Silver Plus Account`. Its documented minimum opening deposit is $1,000, ongoing minimum balance is $2,500, and a balance below that ongoing minimum may incur an $8 monthly maintenance fee. It compounds interest daily, provides 15 free withdrawals per month, supports up to 25 monthly ATM-fee rebates, and includes savings-goals tracking.

Do not promise a linked-checking APY bonus merely because the customer has checking. A Silver Plus Account has a documented linked-checking boost only with a `Blue Account` checking account; other pairings are not documented as qualifying. Credit-card bonuses require an eligible card under the same profile.

Use `scripts/assess_accounts.py` after normalizing tool results to structured JSON if a repeatable check is useful. The helper also accepts the common retrieval aliases `class`, `level`, and `current_holdings` for `account_type`, `account_class`, and `balance`. Treat a `false` result, a nonempty `unknown_fields` list, or a nonempty `blockers` list as a reason not to take the corresponding action.

## Open and fund the savings account

After all eligibility checks pass and the customer has selected the product:

1. Call `open_bank_account_4821` with the verified `user_id`, `account_type` set to `savings`, and the exact confirmed `account_class`.
2. Read the returned new account ID and details; do not assume an ID if the tool does not return one.
3. Ask whether the customer authorizes an immediate transfer of the required opening deposit from a specific eligible checking account.
4. If authorized, verify source-account ownership and sufficient available balance, verify destination ownership, fees, limits, and confirmation, then call `transfer_funds_between_bank_accounts_7291` for the required amount.
5. If the customer declines an immediate transfer, do not transfer. State that the new account must be funded within 30 days by internal transfer or external deposit or it will be closed. Calculate and communicate a calendar deadline from the actual opening time when available.

## Evaluate a checking-account closure

For the specifically requested customer-owned checking account, retrieve fresh account details and its transactions. Confirm:

- The account status is `OPEN`.
- No transaction returned for the account has status `pending`.
- The appropriate early-closure fee and notice period are met.

Known checking closure tiers are:

| Account class | Fee if closed within | Fee | Notice |
|---|---:|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | 30 days | $15 | 0 days |
| Blue Account, Green Account | 60 days | $25 | 3 days |
| Evergreen Account | 90 days | $50 | 7 days |
| Bluest Account | 180 days | $100 | 14 days |

If the closure is inside the applicable early-closure window, the balance must be at least the fee because the fee is deducted directly from that account and no alternative payment method is allowed. If no fee applies, the balance must be exactly $0. The customer cannot bypass a fee by saying that the account is empty.

A notice period must have elapsed before closure. If a closure request is the first recorded notice, explain the earliest permitted closure date, record or preserve the request through the available interaction process, and do not call `close_bank_account_7392` until that date. Treat the customer’s expressed closure request as the notice only if the interaction record is retained and its date is known; otherwise state that notice must be recorded. Immediately before closing, re-check status, balance/fee condition, and pending transactions because they can change during the notice period.

Only then call `close_bank_account_7392` with the verified target `account_id`. Report only the tool-confirmed result. If the tool confirms a closure, tell the customer which account was closed and retain the other account only if the records support that statement.

## Script interface

`scripts/assess_accounts.py` reads one JSON object from standard input and emits one JSON object on standard output. It performs conservative, deterministic checks; it does not call banking tools or change accounts.

Input schema:

```json
{
  "now": "ISO timestamp or MM/DD/YYYY",
  "identity_verified": true,
  "selected_account_class": "official savings class ending in Account",
  "accounts": [
    {
      "account_id": "string",
      "account_type": "checking or savings",
      "account_class": "official class",
      "status": "OPEN",
      "balance": "0.00",
      "date_opened": "ISO date or MM/DD/YYYY",
      "in_collections": false,
      "class": "optional alias for account_type",
      "level": "optional alias for account_class",
      "current_holdings": "optional alias for balance"
    }
  ],
  "target_account_id": "optional closure target ID",
  "transactions": [{"status": "posted or pending"}],
  "closure_notice_given_at": "optional timestamp",
  "funding_deferred": false
}
```

The output contains separate `savings_opening` and `closure` assessments, plus a 30-day `funding_deadline` when `funding_deferred` is true. Missing fields are reported as unknown rather than assumed to pass.

Example runtime call:

```sh
python3 scripts/assess_accounts.py <<'JSON'
{"now":"2026-01-15T10:00:00","accounts":[],"funding_deferred":true}
JSON
```

Before acting on an assessment, validate that its account IDs, dates, statuses, balances, and transactions came from fresh tool results for the verified user. A successful script run is not authorization to perform an account action.

## Customer check-deposit questions

Do not represent an undeposited check as available funds and do not close an account while that deposit is pending. If the customer asks for exact check-deposit steps, use only a documented self-service flow or supported user tool when one is available. Do not invent app menus, deposit cutoffs, funds-availability timing, or a deposit tool. If this workflow has no supported instructions or tool for the requested deposit method, explain that limitation and route the customer to the appropriate deposit-support channel rather than performing an unsupported action. Once the deposit is posted, the customer must still wait for any applicable closure notice and the account must be freshly rechecked.