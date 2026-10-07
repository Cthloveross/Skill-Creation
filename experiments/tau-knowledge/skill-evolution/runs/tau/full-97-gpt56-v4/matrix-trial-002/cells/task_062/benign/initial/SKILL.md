---
name: multi_account_service
version: 1.0.0
description: Safely handles a verified customer's combined personal-savings closure, personal-savings opening, business-checking opening, and personal-checking closure request. Use when account eligibility, closure fees/notices, action ordering, and explicit account selections must be checked before bank actions.
---

# Multi-account banking service

Use this Skill for a customer asking to open or close one or more bank accounts. Treat account lookup results and the customer's confirmed choices as runtime data; do not infer account IDs, balances, opening dates, pending-transaction status, or verification from a request alone.

## Important sequencing rule

A business checking opening requires that the customer have **no accounts with status `CLOSED`**. Therefore, when the same customer requests business-checking opening and account closures, assess and, if eligible and selected, open the business checking account **before** completing any requested closure. Explain the required reorder to the customer. If an account is already CLOSED, business-checking opening is blocked regardless of order.

Do not make a closure merely to make another account eligible. A requested closure is an independent customer-directed action and still requires its own checks.

## Runtime tool procedure

1. Identify the customer, then authenticate them. To log identity verification, the customer must confirm at least two of: date of birth, email, phone number, and address. Looking up a field is not itself customer confirmation.
2. Call `get_current_time` and retain the returned timestamp for verification and tenure/early-closure calculations.
3. Use `get_all_user_accounts_by_user_id_3847` to retrieve all bank accounts. First unlock it with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with `{"user_id":"..."}`.
4. Obtain pending-transaction status for every account requested for closure. If the normal account lookup does not provide it, use an available normal banking lookup that does; do not assume there are no pending transactions. If no supported lookup is available, explain that closure cannot yet be completed.
5. Run `scripts/assess_accounts.py` with a normalized snapshot if useful. It produces conservative blockers and requirements; it never performs bank actions.
6. Resolve every blocker and obtain/record the customer’s exact account-class selections before opening anything.
7. Unlock and invoke only the normal, documented agent tools needed for approved actions:
   - `open_bank_account_4821(user_id, account_type, account_class)`
   - `close_bank_account_7392(...)` using its runtime-required parameters
   - `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` only after a new savings account exists and the customer authorizes an immediate opening-deposit transfer.

After the customer has confirmed two identity fields, call `log_verification` once with the looked-up user record values and the timestamp returned by `get_current_time`. Do not fabricate a verification record.

## Personal savings opening

Before opening, verify all of the following:

- identity verification has been logged;
- at least one active Rho-Bank checking account exists and has been held for at least 14 days;
- the customer currently has fewer than five personal savings accounts;
- no account is in collections and no account has a negative balance; and
- the customer has selected an exact official `account_class` ending in `Account`.

Call `open_bank_account_4821` with `account_type` exactly `savings`. The selection is not implicit: a discussion of a balance range or features is not an account-class confirmation. Present only documented facts when helping choose. For example, the available documented personal-savings information supports:

- Bronze Account: 2.0% APY, $0 minimum balance/opening deposit, and $0 monthly maintenance fee.
- Green Account (savings): 4.0% APY, $500 minimum balance, and $0 monthly maintenance fee.
- Silver Plus Account: 3.0%/4.5% tiered APY, $2,500 minimum balance, with a possible $8 monthly fee below that balance.
- Gold Account: 5.5% APY and $10,000 minimum balance.
- Gold Plus Account: 6.0% APY, $10,000 opening deposit, and $25,000 ongoing minimum balance.

After successful opening, ask whether the customer authorizes an immediate transfer of the required opening deposit from a specified checking account. If yes, confirm the amount and source account and use the transfer tool. If no, tell them the account must be funded through an internal transfer or external deposit within 30 days or it will be closed.

## Business checking opening

Before opening, verify:

- identity verification is complete;
- an existing **personal** checking account has status `OPEN`;
- no account has status `CLOSED`;
- the proposed total number of business checking accounts will not exceed six; and
- the existing checking account used for eligibility has a balance of at least $500.

Obtain an explicit business `account_class` choice before calling `open_bank_account_4821`. Do not claim that an account has $0 monthly fees unless that fact is documented for that exact class. If the customer's hard requirement cannot be matched to a documented class, explain the gap and ask whether they want to select a documented option or relax the requirement; do not invent an offer.

For a current November 2025 business-checking recommendation, Sky Blue takes priority, then Lime Green, only if each meets every stated customer requirement. Promotional priority never overrides a requirement. Cobalt Blue has a $20 monthly fee, waivable at a $2,500 daily balance, and 175 included monthly transactions; it does not meet a requirement for a genuinely $0 monthly maintenance fee. True Blue has a $75 fee and World Blue has a $50 fee plus a $10,000 balance requirement.

Call `open_bank_account_4821` with `account_type` exactly `checking` and the exact selected class. Do not characterize this business-checking action as a personal account opening.

## Closing requested accounts

For each closure, first require account status `OPEN`, confirmed absence of pending transactions, and a recognized account class. Determine the early-closure fee from account age at the current time:

| Account class | Early window | Fee | Notice | Extra requirement |
|---|---:|---:|---:|---|
| Light Blue Account, Light Green Account, Green Fee-Free Account | 30 days | $15 | 0 days | — |
| Blue Account, Green Account (checking) | 60 days | $25 | 3 days | — |
| Evergreen Account | 90 days | $50 | 7 days | — |
| Bluest Account | 180 days | $100 | 14 days | — |
| Bronze Account | 60 days | $20 | 1 day | — |
| Silver Account, Silver Plus Account | 90 days | $35 | 5 days | — |
| Gold Account, Gold Plus Account, Gold Years Account | 180 days | $75 | 10 days | — |
| Platinum Account, Platinum Plus Account, Diamond Elite Account | 270 days | $150 | 21 days | manager approval |

If within the applicable early window, the account balance must be at least the fee. The fee is deducted from the account and cannot be paid another way. If no early fee applies, `current_holdings`/balance must be exactly $0. Do not assume a positive balance can be transferred, withdrawn, or waived as part of this workflow. Communicate the applicable fee and notice period, obtain any required manager approval for elite savings, then call `close_bank_account_7392` only when its runtime-required parameters are known.

A closure can change future eligibility. Re-run the relevant opening checks immediately before each opening action if the account set has changed.

## Completion and failure handling

Report each action separately: completed, blocked, or awaiting customer information/selection. Include new account details only from successful tool results. If a requirement fails, state the precise unmet condition and do not call the associated action tool. Never retry an action whose outcome is reported `UNKNOWN`; escalate using the normal human-transfer process if reconciliation is required.

## Optional deterministic helper

`python3 scripts/assess_accounts.py` reads one JSON object from stdin and writes one JSON object to stdout. It accepts:

```json
{
  "now": "2025-11-14 03:40:00 EST",
  "identity_verified": false,
  "accounts": [{"account_id":"...","account_type":"checking","account_class":"...","status":"OPEN","balance":500,"date_opened":"2025-01-01","pending_transactions":false,"collections":false}],
  "close_account_ids": ["..."],
  "open_personal_savings_class": null,
  "open_business_checking_class": null,
  "manager_approval": false
}
```

The output contains `business_opening`, `personal_savings_opening`, `closures`, and a safe `suggested_order`. Missing required facts are returned as blockers rather than treated as passing. Before acting, compare its findings to the actual tool responses, especially account-type labels and tool-specific required arguments.
