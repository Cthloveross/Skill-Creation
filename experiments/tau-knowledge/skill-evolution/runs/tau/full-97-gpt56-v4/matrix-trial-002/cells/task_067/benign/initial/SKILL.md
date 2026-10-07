---
name: checking-switch-and-high-yield-savings
version: 1.0.0
description: Safely handles a customer request to replace a personal checking account and open a high-yield personal savings account. Use for authenticated Rho-Bank customers when account opening, closure prerequisites, linked APY boosts, eligibility, funding, and product tradeoffs must be evaluated.
---

# Checking Switch and High-Yield Savings

Use this Skill for a requested checking-account replacement combined with a savings-account recommendation or opening. It enforces identity verification, opening eligibility, closure conditions, and the correct action sequence. It does **not** authorize actions automatically: the executor must use the declared bank tools after the relevant checks and customer confirmations.

## Important ordering

Do not close the customer's existing checking account before a replacement checking account is successfully opened. Personal savings eligibility requires an active checking account with at least 14 days' tenure. The existing account may be the account satisfying that tenure requirement; preserve it until savings eligibility, funding, and the new checking account are resolved.

Do not represent an account as the universally best option without stating relevant opening and ongoing-balance conditions. For a customer optimizing APY, distinguish:

- the maximum documented nominal/effective APY available to the customer;
- whether the customer's available funds meet the opening minimum; and
- whether the customer can maintain the ongoing minimum.

Use `references/product_catalog.json` only as a documented product comparison aid. Confirm the final account-class string with the customer. The full official class name ending in `Account` is required by the opening tool.

## Required workflow

### 1. Authenticate and locate the customer

1. Obtain an email address or user ID only to locate the record.
2. Retrieve the customer record with the matching read-only lookup tool.
3. Verify identity by having the customer confirm at least two of the four identity fields: date of birth, email address, phone number, and address. Do not expose unconfirmed sensitive values as a verification prompt.
4. Call `get_current_time`, then call `log_verification` with the complete retrieved record and timestamp after two fields are confirmed.
5. Do not open, close, or transfer funds until verification is logged.

### 2. Collect live account and transaction facts

Unlock and use the documented internal tools as needed:

- `get_all_user_accounts_by_user_id_3847(user_id)` for all checking and savings accounts, including status, balance, and opening date.
- `get_bank_account_transactions_9173(account_id)` for the account proposed for closure. Check every returned transaction for `status: pending`.
- `get_credit_card_accounts_by_user(user_id)` when calculating an APY that may be affected by card bonuses.

Record the exact target account ID, class, status, balance/current holdings, and opening date. Resolve ambiguous status, account ownership, balances, or transaction status before proceeding.

### 3. Check all eligibility before offering an action

For a new **personal checking** account, confirm:

- verified customer;
- age at least 18;
- fewer than four existing personal checking accounts before opening another;
- no checking account closed for cause in the previous six months.

For a new **personal savings** account, confirm:

- verified customer;
- an ACTIVE or OPEN checking account held for at least 14 days;
- fewer than five personal savings accounts;
- no account in collections; and
- no negative balance on any account.

If a required fact cannot be obtained, do not infer it from the customer's request. Explain what prevents completion and obtain the missing information or use the appropriate available account data. If an eligibility condition fails, do not call an opening tool.

### 4. Present a compliant recommendation and obtain selections

For an APY-focused request, use the catalog and the customer's actual age, funds, checking accounts, and cards. Evaluate linked boosts carefully:

- Only documented checking/savings pairings qualify.
- If more than one checking boost applies, use only the single highest checking boost; never add checking boosts together.
- Add a credit-card bonus only if documentation for the selected savings account supports it. When multiple card bonuses are relevant, use the highest applicable card bonus, not a sum.
- Other bonus categories must not be assumed.

Explain opening and ongoing minimums, any maintenance-fee implications, and whether the proposed transfer source has enough money. If the highest-rate alternative cannot be maintained with the stated funds, present a sustainable alternative and let the customer choose. Confirm separately:

1. the exact replacement checking `account_class`;
2. the exact savings `account_class`;
3. the source account and positive USD amount for any immediate opening-deposit transfer; and
4. authority to perform the transfer.

### 5. Open accounts in safe order

After checking eligibility and account-class confirmation:

1. Unlock and call `open_bank_account_4821` for the replacement checking account using `account_type: "checking"` and the full official `account_class`.
2. Re-check the new account result and retain its ID.
3. Check savings eligibility again. In particular, identify which active checking account has the required 14-day tenure; a just-opened replacement normally does not.
4. Call `open_bank_account_4821` for the selected savings account using `account_type: "savings"` and its full official name.
5. If the customer authorizes immediate funding, ensure both accounts are ACTIVE or OPEN, are owned by the customer, are distinct, and the source has sufficient available funds. Unlock and call `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` with a positive USD amount.
6. If the customer declines an immediate transfer, clearly disclose the 30-day funding deadline and that an unfunded savings account will be closed. Do not fabricate a transfer.

A documented savings opening minimum is a product requirement. Do not say a savings account is funded merely because it was opened; verify the transfer result or disclose the outstanding funding requirement.

### 6. Close the old checking account last

Before closing, require all of the following for the exact target account:

- account status is exactly `OPEN`;
- transaction history was retrieved and contains no pending transaction;
- the tier-specific notice period has elapsed or is zero; and
- its balance is zero when no early closure fee applies, or its balance is at least the full early closure fee when a fee applies. The fee is deducted from the account itself; it cannot be paid from another account.

Tier rules:

| Tier | Account classes | Early fee | Fee window | Notice |
|---|---|---:|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 | first 30 days | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 | first 60 days | 3 days |
| Premium | Evergreen Account | $50 | first 90 days | 7 days |
| Elite | Bluest Account | $100 | first 180 days | 14 days |

Do not make a balancing transfer merely to bypass the rule. For example, an early-closing account with a $15 fee needs at least $15 in that same account; a zero balance is not sufficient during the fee window. Once all conditions are satisfied, unlock and call `close_bank_account_7392` with the tool's required account identifier. Confirm the result, including any fee applied.

## Deterministic evaluator

Use `scripts/account_workflow.py` to calculate mechanical eligibility, closure fee conditions, and documented APY comparisons from live data. It is a decision aid, not a replacement for live-tool validation.

The script reads one JSON object from stdin and writes one JSON object to stdout. Input schema:

```json
{
  "as_of": "YYYY-MM-DD or timestamp",
  "customer": {"verified": true, "date_of_birth": "MM/DD/YYYY"},
  "accounts": [{"account_id": "...", "account_type": "checking|savings", "account_class": "...", "status": "OPEN", "balance": 0, "date_opened": "MM/DD/YYYY", "in_collections": false}],
  "checking_closure_for_cause_last_6_months": false,
  "closing_account_id": "...",
  "closing_transactions": [{"status": "posted"}],
  "transactions_retrieved": true,
  "available_savings_funds": 0,
  "savings_options": [{"account_class": "...", "base_apy": 0, "opening_minimum": 0, "ongoing_minimum": 0, "checking_boosts": [{"checking_class": "...", "apy_bonus": 0}], "card_bonuses": [{"card_class": "...", "apy_bonus": 0}]}],
  "held_card_classes": []
}
```

Dates may be `MM/DD/YYYY`, `YYYY-MM-DD`, or ISO timestamps. `checking_closure_for_cause_last_6_months` must be explicitly `true` or `false`; omit it when unknown. `savings_options` is optional. If supplied, the script ranks only the supplied documented options. Its output contains `checking_opening`, `savings_opening`, `closure`, `savings_comparisons`, and a `blocks` list. Treat any `eligible: false`, closure `may_close_now: false`, or nonempty `blocks` as a stop condition for the affected action.

Example runnable call (replace all values with current live facts):

```sh
python3 scripts/account_workflow.py <<'JSON'
{"as_of":"2025-01-01","customer":{"verified":true,"date_of_birth":"01/01/1990"},"accounts":[],"checking_closure_for_cause_last_6_months":false,"transactions_retrieved":false}
JSON
```

Validate the output before acting: account counts must agree with the retrieved account list, `pending_transaction_count` must match transaction records, the fee/notice result must match the target class and opening date, and every APY comparison must identify its specific applied checking/card boosts and funding/minimum results.

## Failure handling and customer response

- Never retry an operation reported as `UNKNOWN`.
- If the customer declines required identity confirmation, cannot meet eligibility, has pending transactions, lacks funds for an early closure fee, or has not completed a required notice period, do not perform the blocked action. State the precise next step.
- If a tool fails after an action might have posted, inspect the returned status and do not duplicate the action.
- Do not tell the customer to call internal tools or expose internal IDs beyond what is appropriate for confirmation.
- Summarize completed account openings, transfer amount/source/destination, remaining funding deadline if applicable, closure status, fee, and any unresolved condition.
