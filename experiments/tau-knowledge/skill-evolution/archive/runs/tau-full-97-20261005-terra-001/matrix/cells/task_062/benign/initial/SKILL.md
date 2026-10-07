---
name: bank-account-overhaul-workflow
description: Safely handle a customer request that combines personal savings or checking closures, a business-checking opening, and a personal-savings opening. Use when eligibility, account status, balances, pending transactions, opening deposits, exact account classes, and action ordering must be checked before using Rho-Bank account tools.
---

# Bank Account Overhaul Workflow

Use this Skill for multi-action banking requests. It deliberately separates verification, fact gathering, eligibility decisions, customer authorizations, and irreversible account actions. Never infer account IDs, balances, dates, identity confirmation, selected account classes, or permission to move money.

## Runtime inputs and tool discovery

1. Identify the authenticated profile using a supplied identifier or the appropriate user lookup.
2. Verify identity by having the customer confirm **two of the four** profile fields: date of birth, email, phone number, and address. Do not count information merely retrieved from the profile as a confirmation.
3. After two fields are confirmed, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete profile values and that timestamp. Do not perform opening, closing, or transfer actions before this succeeds.
4. Unlock the needed internal tools before use. The supplied procedures identify these tools:
   - `get_all_user_accounts_by_user_id_3847` for account IDs, types, classes, statuses, balances, and opening dates.
   - `get_bank_account_transactions_9173` for pending-transaction checks on each account proposed for closure.
   - `open_bank_account_4821` for supported account openings.
   - `transfer_funds_between_bank_accounts_7291` for authorized internal transfers.
   - `close_bank_account_7392` for account closure.
5. Use only documented parameters. In particular, use `open_bank_account_4821(user_id, account_type, account_class)` and `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`. If a closure tool requires arguments not specified in the procedure, obtain its runtime contract after unlock rather than guessing.

The agent—not the customer—calls internal banking tools.

## Gather and normalize facts

Retrieve all customer bank accounts, then retrieve transactions for every account to be closed. Normalize the account records and run:

```text
python3 scripts/evaluate_account_workflow.py <<'JSON'
{
  "now": "2025-01-31 12:00:00 EST",
  "identity_verified": true,
  "accounts": [{"account_id":"...","account_type":"savings","account_class":"Bronze Account","status":"OPEN","balance":0,"date_opened":"2024-12-01"}],
  "transactions_by_account": {"...": [{"status":"posted"}]},
  "business_account_class": "Navy Blue",
  "personal_savings_account_class": "Silver Account"
}
JSON
```

The script reads one JSON object from stdin and writes one JSON result to stdout. It accepts dates in `YYYY-MM-DD`, `MM/DD/YYYY`, or a timestamp beginning with one of those formats. `balance` may be a JSON number or a numeric string. Optional `is_personal_checking` on checking accounts resolves whether the account is personal where account data otherwise cannot establish that fact. An absent value is reported as an evidence gap, not silently assumed.

Review `blocking_reasons`, `evidence_gaps`, `openings`, and `closures` in its output. The script is a decision aid; tool-returned facts and the governing procedure remain authoritative.

## Required decisions

### Business checking

For a business checking opening, verify all of the following before opening:

- identity is verified;
- at least one existing **personal** checking account has status `OPEN`;
- that qualifying checking account has balance at least $500;
- the customer will remain at no more than six business checking accounts (there must be capacity before a new one is opened);
- no account currently has status `CLOSED`.

The customer must select the account class. Match the stated selection to the documented product information; do not claim a feature that is not sourced. For a request for a permanent $0 monthly maintenance fee, Navy Blue is supported by the supplied product material as having a $0.00 monthly maintenance fee. It may be opened only after the business eligibility checks pass.

### Personal savings

Before opening personal savings, verify:

- identity is verified;
- at least one active Rho-Bank checking account exists and has been held at least 14 days;
- the customer currently has fewer than five personal savings accounts;
- there are no accounts in collections and no negative account balances;
- the customer has explicitly confirmed an exact full official `account_class` ending in `Account`.

A balance range or desired features does **not** select an account. Explain supported options when relevant and request a precise choice. For example, Silver Account has a $500 opening deposit and $1,000 ongoing minimum; Silver Plus Account has a $1,000 opening deposit and $2,500 ongoing minimum. Obtain the chosen full class name before the opening call.

After a successful opening, ask whether the customer authorizes an immediate opening-deposit transfer from a named checking account. If yes, validate both accounts are `OPEN` or `ACTIVE`, belong to the customer, have distinct IDs, and that the source has sufficient funds; then transfer the documented required positive amount. If no, state that the account must be funded within 30 days by internal transfer or external deposit or it will close.

### Closures

For each requested closure, require an `OPEN` account and no transaction with status `pending`. Also apply the balance rule:

- when an early-closure fee applies, account balance must cover the fee;
- otherwise, the account balance must be $0.

Do not transfer a residual balance merely because closure was requested. Obtain the customer’s authorization, source account, destination account, and amount first. Validate the transfer requirements before calling the transfer tool.

Use the following supplied personal-account rules:

| Account class | Early fee window and fee | Notice period |
| --- | --- | --- |
| Bronze Account (savings) | $20 if closed within 60 days | 1 day |
| Evergreen Account (checking) | $50 if closed within 90 days | 7 days |

Clearly tell the customer whether the fee and notice period apply based on opening date and current time. If closure cannot proceed, explain the specific blocker (pending transaction, nonzero balance when no fee applies, insufficient balance for an applicable fee, or account not open) and stop that closure.

## Safe action ordering

For a request that combines the actions above, do not close accounts first. A `CLOSED` account blocks the documented business-checking eligibility check, and closing the only usable checking account can block personal-savings eligibility or funding. Subject to all checks passing, use this order:

1. Complete identity verification, gather accounts and closure transactions, and resolve all evidence gaps.
2. Obtain any missing exact personal savings class, funding decision, and balance-disposition authorization.
3. Open business checking while there are no closed accounts and its personal-checking eligibility is still satisfied.
4. Open personal savings while a qualifying active checking account remains available; arrange its opening deposit only if authorized.
5. Make any separately authorized transfers needed to meet closure balance requirements.
6. Process each eligible closure, honoring its notice period and tool outcome.
7. Re-check account details/transactions where the runtime supports it, avoid duplicates, and provide a concise completion summary: opened account details, each transfer and funding status, each closure outcome, applicable fees/notices, and outstanding actions or deadlines.

If eligibility requires closure of an account first, explain the conflict rather than performing actions in an order that creates a documented eligibility failure. If a requirement cannot be verified from available data, do not proceed with the affected action.

## Validation

Before every mutation, confirm the relevant account IDs came from the current lookup, the latest eligibility result has no blocker, the customer authorization applies to the exact action, and no prior call already completed it. After a transfer, confirm it posted and do not retry blindly. After an opening or closure, use the tool result and any available account lookup to report only confirmed outcomes.
