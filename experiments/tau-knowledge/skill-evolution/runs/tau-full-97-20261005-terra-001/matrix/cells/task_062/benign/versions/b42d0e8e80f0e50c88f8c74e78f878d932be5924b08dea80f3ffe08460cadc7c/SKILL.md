---
name: bank-account-overhaul-workflow
description: Handle combined requests to open business checking and personal savings accounts and to close existing checking or savings accounts. Use when product selection, eligibility, customer authentication, funding, balance disposition, pending transactions, and safe sequencing must be assessed before Rho-Bank account actions.
---

# Bank Account Overhaul Workflow

Use this Skill for multi-action banking requests. Separate factual product guidance, eligibility checks, customer authorization, and account mutations. Never infer an account ID, account balance, opening date, account selection, destination, or authorization to move funds.

The agent, not the customer, performs internal banking actions.

## 1. Authenticate and gather current facts

1. Locate the customer profile using the information supplied by the customer.
2. Have the customer confirm two of these profile fields: date of birth, email, phone number, or address. Retrieved profile data alone is not a confirmation.
3. After confirmation, get the current timestamp and call `log_verification` using the complete profile and timestamp. Do not perform an opening, transfer, or closure before verification succeeds.
4. Unlock and use these documented agent tools as needed:
   - `get_all_user_accounts_by_user_id_3847(user_id)` for account IDs, type, class, status, balance, and opening date.
   - `get_bank_account_transactions_9173(account_id)` for every account requested for closure.
   - `open_bank_account_4821(user_id, account_type, account_class)` to open an account.
   - `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` for an authorized internal transfer.
   - `close_bank_account_7392` only after its runtime contract has been unlocked and all closure conditions are met.
5. Treat the current account lookup and transaction results as the authoritative runtime evidence. Do not invent classifications not returned by the lookup. A checking account that is not identified as business may be treated as personal only when the returned data establishes that it is a personal checking account.

Use this optional decision aid after normalizing tool results:

```text
python3 scripts/evaluate_account_workflow.py <<'JSON'
{
  "now": "2025-01-31 12:00:00 EST",
  "identity_verified": true,
  "accounts": [
    {"account_id": "...", "account_type": "checking", "account_class": "...", "status": "OPEN", "balance": "500.00", "date_opened": "2024-01-01", "is_business": false}
  ],
  "transactions_by_account": {"...": [{"status": "posted"}]},
  "business_account_class": "Navy Blue",
  "personal_savings_account_class": "Silver Plus Account",
  "close_account_ids": ["..."]
}
JSON
```

The script receives one JSON object on stdin and emits one JSON object on stdout. It does not call banking tools or authorize actions. It accepts dates beginning `YYYY-MM-DD` or `MM/DD/YYYY`, and numeric or numeric-string balances. Review its evidence gaps and action-specific results against the actual tool records before acting.

## 2. Give accurate product guidance

Answer product questions from the supplied guides rather than saying documented facts are unavailable.

### Navy Blue business checking

- Navy Blue has a **$0.00 monthly maintenance fee** and **no minimum balance requirement**.
- It supports unlimited digital transfers subject to a $25,000 daily digital-transfer limit and has a 0.5% APY.
- Do **not** describe it as universally or genuinely fee-free. Optional or usage-based charges can still apply: domestic wires cost $15, same-day ACH costs $5, U.S. out-of-network ATM withdrawals cost $2.50, and foreign ATM withdrawals cost 3% with a $5 minimum. Standard ACH is not charged.
- If a customer whose requirement was “no fees” selects Navy Blue, clearly distinguish the permanent $0 monthly maintenance fee from the possible service fees, then honor the explicit selection if they proceed.

### Silver and Silver Plus savings

- Silver Plus requires a $1,000 opening deposit and a $2,500 ongoing minimum balance. It compounds interest daily, provides up to 15 free withdrawals per month, and has tiered 3.0% / 4.5% APY depending on the stated tier threshold.
- Silver requires a $500 opening deposit and a $1,000 ongoing minimum balance. It compounds daily and has 10 free withdrawals per statement cycle.
- Silver Plus documentation provides a 0.025% relationship APY bonus when the relationship criteria are met and ATM-fee rebates up to 25 each month. Silver documentation describes a 0.025% relationship APY bonus for eligible customers and ATM-fee rebates up to 15 each month.
- Do not promise a relationship benefit unless the applicable qualification criteria are met. Explain the documented feature and qualification condition instead.

A budget range or feature preference is not itself an account selection. Obtain an explicit exact personal-savings class ending in `Account` before opening savings. Conversely, an explicit customer selection such as “Let’s go with [product]” is a selection; do not unnecessarily re-request it.

## 3. Evaluate opening eligibility

### Business checking

Before opening business checking, verify all of these from current evidence:

- identity verification is logged;
- the customer has at least one existing personal checking account with status `OPEN`;
- an eligible existing checking account has a balance of at least $500;
- the customer currently has fewer than six business checking accounts;
- no account has status `CLOSED`; and
- the customer selected a business checking class.

When satisfied, call `open_bank_account_4821` with `account_type: "checking"` and the customer-selected business class. Do not delay this eligible opening because a separate requested closure has a balance-disposition issue.

### Personal savings

Before opening personal savings, verify:

- identity verification is logged;
- at least one active Rho-Bank checking account exists and has been open at least 14 days;
- the customer has fewer than five personal savings accounts;
- no account is in collections and none has a negative balance; and
- the customer explicitly selected the full official savings class ending in `Account`.

When satisfied, call `open_bank_account_4821` with `account_type: "savings"` and the exact selected class. Do not substitute or abbreviate the class name.

After a successful savings opening, ask whether the customer authorizes an immediate opening-deposit transfer from a specified checking account. If yes, validate both accounts are open or active, belong to the customer, have distinct IDs, and the source has sufficient funds; then transfer the documented required positive opening-deposit amount. If the customer declines or defers funding, do not transfer. State clearly that the new savings account must be funded by internal transfer or external deposit within **30 days** or it will be closed.

## 4. Handle closures without unauthorized movement of money

For each requested closure, retrieve its transaction history and require that:

- the account is `OPEN`;
- it has no pending transaction;
- the opening date and current time establish any applicable early-fee window and notice period; and
- its balance is handled in accordance with the closure rule.

Documented relevant tiers are:

| Account class | Early closure fee | Notice period |
|---|---:|---:|
| Bronze Account (savings) | $20 if closed within 60 days | 1 day |
| Evergreen Account (checking) | $50 if closed within 90 days | 7 days |

Never treat a request to close an account as permission to transfer its balance. For a nonzero balance, obtain explicit authorization for the exact source account, destination account, and amount before any transfer. Validate ownership, status, distinct IDs, and sufficient source funds. If no authorized destination and amount are supplied, do not transfer and do not close the account. Explain that the account remains open pending instructions for its balance. Do not use a newly opened account as a destination unless the customer specifically authorizes that destination and transfer.

A closure fee does not erase the need to resolve any remaining funds or meet the account’s stated closure conditions. Observe the applicable notice period and the closure tool’s runtime requirements. Do not guess unprovided closure-tool parameters.

## 5. Safe sequence and completion

For a combined request, use this order when the prerequisites are met:

1. Authenticate, log verification, retrieve accounts, and retrieve closure transactions.
2. Explain requested product facts and obtain missing exact account selections, funding choices, or balance-disposition authorizations.
3. Open eligible business checking before any closure, because a closed account blocks business-checking eligibility.
4. Open eligible personal savings while a qualifying checking account remains active.
5. Perform only separately authorized savings funding or closure-balance transfers.
6. Close only accounts that meet their own balance, pending-transaction, fee, notice, and tool requirements.
7. Confirm only tool-reported outcomes and provide a concise summary of openings, funding status/deadline, transfers, closures, fees/notices, and remaining customer decisions.

Before every mutation, ensure the customer authorization applies to the exact operation, input IDs are from the current lookup, and the action has not already been completed. On a tool error, report it and re-check facts; never blindly retry a mutation.
