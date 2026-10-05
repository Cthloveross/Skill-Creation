---
name: close-personal-checking-account
description: Verify and process a customer-requested closure of a personal checking account, including identity/ownership checks, account balance and early-fee rules, pending transactions, associated debit cards, and tier-specific notice periods. Use when a customer asks to close a checking account; defer unrelated requests such as opening a savings account until the closure request is resolved.
---

# Close Personal Checking Account

## Scope and assumptions

This workflow applies to personal checking accounts. It uses the customer’s requested product/account selection at runtime; do not infer that another account should be closed merely because it has a similar name. A request to keep a different account is not authorization to alter that other account.

The customer must make the closure request and identify the target account. If the customer asks for multiple services, complete or resolve the closure request first and return to the other service only if the customer still wants it.

## Required checks before any banking action

Before retrieving account-specific banking data or initiating a closure:

1. Verify identity by having the customer confirm at least two of these profile fields: date of birth, email, phone number, and address. Compare customer-provided values against the authoritative user profile. A name alone is not one of the two required fields.
2. Obtain the current time with `get_current_time` and call `log_verification` after successful verification. Populate every required logging field from the authoritative profile and use the returned current timestamp.
3. Resolve the user record and retain the verified `user_id`. Confirm the requested target account belongs to that verified user. If account ownership cannot be established, do not disclose account details or proceed.
4. Confirm the customer’s intent to close the specifically selected account. The request itself is the closure authorization unless the active closure tool or an applicable procedure explicitly requires an additional confirmation. Do not invent a confirmation requirement.

If identity, authority, ownership, or product eligibility is not established, stop and explain the missing requirement without performing the closure.

## Runtime tool sequence

The named banking tools are discoverable agent tools. Before first use of each one, call `unlock_discoverable_agent_tool` with its exact name; then call it via `call_discoverable_agent_tool` using the parameters below. Use the actual unlocked tool schema where documentation does not state a parameter schema.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
   - Locate the exact requested checking account.
   - Verify it is a checking account, is owned by the verified customer, and capture `account_id`, account class, status, balance, and date opened.
   - Do not use an account from a different user or a savings account.
2. Unlock and call `get_bank_account_transactions_9173` with the target `account_id`.
   - Inspect all returned transactions. Any transaction whose status is `pending` blocks closure, irrespective of amount or transaction type.
3. Unlock and call `get_debit_cards_by_account_id_7823` with the target checking `account_id`.
   - Any associated card not already `CLOSED` must be resolved before the checking account can close.
   - For each card that must be closed, follow the debit-card closure requirements: verify ownership, confirm it is `ACTIVE` or `PENDING`, check for pending/processing card transactions and pending refunds, and check the 14-day minimum card age unless the customer’s supported reason is lost, stolen, or suspected fraud. Do not claim that an account-level transaction lookup proves there are no pending card refunds.
   - When eligible and the customer has supplied a valid reason, unlock and use `close_debit_card_4721` with `card_id` and `reason`. For an account-closure-related card closure, use the documented `account_closing` reason. Re-query cards to confirm no associated card remains open. If a card status is unsupported for closure, or a card prerequisite cannot be checked with available supported tools, do not close the checking account; explain the blocker or use the established escalation path.
4. Determine fee and notice requirements from the table below, using the account’s actual class and date opened. Use the current time gathered at verification. `scripts/assess_checking_closure.py` can calculate these determinations from normalized tool results, but it does not replace source-of-record checks.
5. Only after every prerequisite and the applicable notice period are satisfied, unlock `close_bank_account_7392` and invoke it with the target account using the unlocked tool’s actual schema. Do not guess parameters that were not documented or shown by the tool.
6. Report the resulting outcome only after the closure tool returns. State the closed account identifier/product as appropriate, any fee actually assessed, and that the account cannot be treated as closed if the tool failed or returned an unresolved status.

## Closure policy

The account must be `OPEN` and have no pending account transactions.

| Account tier / recognized class | Early-closure window and fee | Required notice |
| --- | --- | --- |
| Light Blue Account, Light Green Account, Green Fee-Free Account | $15 if closed within 30 days of opening | 0 days |
| Blue Account, Green Account (checking) | $25 if closed within 60 days of opening | 3 days |
| Evergreen Account | $50 if closed within 90 days of opening | 7 days |
| Bluest Account | $100 if closed within 180 days of opening | 14 days |

Interpret “within” as fewer elapsed days than the specified window. If the account class is not one of these recognized checking products, do not guess a tier or fee; obtain the applicable policy before closing.

Balance rule:

- If an early-closure fee applies, the balance must be at least that fee. The fee is deducted directly from the account; no alternate payment method may be offered.
- If no early-closure fee applies, the balance must be exactly $0.

Notice rule:

- Treat the customer’s closure request as notice only when no earlier recorded notice is available.
- A closure action may occur only once the tier’s full notice interval has elapsed. Record or communicate the earliest eligible closure time using the current verified timestamp and the required number of calendar days.
- Where a nonzero notice period has just begun and no supported tool exists to register/schedule it, do not call the close tool early. Tell the customer the date/time after which they can continue the request. Do not represent the account as closed.

## Deterministic assessment helper

Use `scripts/assess_checking_closure.py` after converting tool responses into the input schema below. It is advisory: the executor must still ensure identity logging, ownership, card-specific closure prerequisites, and actual closure-tool success.

### Input JSON

```json
{
  "as_of": "ISO-8601 timestamp or YYYY-MM-DD",
  "account": {
    "account_id": "string",
    "account_type": "checking",
    "account_class": "policy product name",
    "status": "OPEN",
    "balance": "decimal USD string or number",
    "date_opened": "ISO-8601 timestamp or YYYY-MM-DD"
  },
  "transactions": [{"status": "posted or pending"}],
  "debit_cards": [{"status": "CLOSED, ACTIVE, PENDING, FROZEN, or other"}],
  "identity_verified": true,
  "ownership_verified": true,
  "notice_given_at": "optional ISO-8601 timestamp or YYYY-MM-DD"
}
```

`as_of`, `account`, `transactions`, and `debit_cards` must be supplied from current tool results. Omit `notice_given_at` when no prior recorded notice exists. Amounts are handled with decimal arithmetic, not binary floating point.

### Output JSON

The script emits an object with `eligible_to_close`, `blockers`, `requirements`, `early_fee`, `early_fee_applies`, `earliest_close_at`, and a normalized account summary. `eligible_to_close: true` means the supplied facts meet the account-level policy checks; it is not proof that debit-card-specific pending-refund and card-age checks were completed, nor that the closure tool has succeeded.

Run it by writing the normalized current facts to a file and piping that file to the script:

```sh
python3 scripts/assess_checking_closure.py < closure_request.json
```

Validate that stdout is a single JSON object, `blockers` is empty before attempting closure, `eligible_to_close` is true, and the target account ID still matches the account selected from the live lookup. If parsing fails or fields are missing, treat the assessment as unavailable and manually resolve the missing data; do not close based on assumptions.

## Customer-facing failure handling

State the specific blocker without exposing unrelated account information: failed verification, account not open, unknown product tier, pending transaction, insufficient balance for an applicable fee, nonzero balance after the fee window, outstanding debit card, or unmet notice period. Do not move funds, waive fees, close cards, or close accounts merely to satisfy a prerequisite unless the customer requested and authorized the separate action and its own documented controls are met.
