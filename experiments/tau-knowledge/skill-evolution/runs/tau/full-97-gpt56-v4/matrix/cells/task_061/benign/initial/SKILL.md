---
name: verified-checking-account-closure
description: Verify a customer and safely process or prepare a personal checking-account closure, including account-tier fees, notice periods, pending transactions, and linked debit cards. Use when a customer asks to close a checking account; defer unrelated account-opening work unless the customer wants to resume it.
---

# Verified checking-account closure

## Scope and safety rules

Use this Skill for a requested closure of a personal checking account. Do not close a similarly named account by inference: identify the requested account from the customer's account records and preserve every account the customer did not request to close.

Do not call a closure tool until identity verification, account eligibility, debit-card requirements, and the applicable notice period have all been satisfied. A customer statement about a balance, account age, pending activity, or cards is not a substitute for the required record checks.

If the customer postpones another request (for example, opening a savings account), acknowledge it and leave it unperformed. Do not recommend or open a savings account during this closure workflow unless the customer asks to resume that topic.

## 1. Verify the customer before account actions

1. Locate the customer using the information they supplied with `get_user_information_by_name` or `get_user_information_by_email`. Resolve ambiguity before proceeding.
2. Ask the customer to confirm at least two of these four profile fields: date of birth, email, phone number, and address. Compare the confirmations to the retrieved profile without unnecessarily disclosing the stored values.
3. Obtain the timestamp with `get_current_time` and call `log_verification` only after two fields match. Supply the complete retrieved profile and the timestamp required by that tool.
4. If identity cannot be verified, do not retrieve or act on accounts. Explain that verification is required; transfer only when a transfer is appropriate for the unresolved situation.

## 2. Retrieve the exact account and current closure facts

Unlock and call the documented agent tools as needed:

- `get_all_user_accounts_by_user_id_3847` with `user_id` to retrieve account ID, type/class, status, balance, and opening date.
- `get_bank_account_transactions_9173` with `account_id` to retrieve account transactions and their statuses.
- `get_debit_cards_by_account_id_7823` with `account_id` to retrieve every debit card linked to the checking account.

Use the returned account ID for all subsequent checks. Confirm that the selected record is the customer-requested checking account, is `OPEN`, and has a recognizable account class. Check the transaction results for any `pending` status; pending transactions block closure.

For a checking account, every associated debit card must already be closed before the account can be closed. A card with `ACTIVE`, `PENDING`, `FROZEN`, or any other non-`CLOSED` status blocks account closure.

### Closing linked debit cards

When a non-closed linked card exists, explain that it must be closed first. The account-closure request supports the debit-card reason `account_closing`, but still complete the card-specific eligibility review before closing it:

- the customer is verified and owns the card;
- the card is currently `ACTIVE` or `PENDING`;
- it has no pending/processing transactions or pending refunds; and
- it has been active at least 14 days, calculated from `date_issued`.

The 14-day rule is bypassed only for `lost`, `stolen`, or `fraud_suspected`, not merely because the checking account is being closed. Do not claim the pending-transaction or refund condition is clear unless it has been checked with an available supported source. If all card conditions are met, unlock `close_debit_card_4721` and call it with the documented `card_id` and `reason` fields. Tell the customer that the card is permanent deactivated and recurring payments need updated payment information. Then refresh the debit-card lookup before resuming account closure.

If a required card check cannot be performed with the available tools, do not assume it passes and do not close the checking account. Clearly state the unresolved prerequisite; use an appropriate human handoff only if it is necessary to resolve it.

## 3. Determine tier, fee, and notice period

Apply these rules based on the exact account class:

| Account tier | Account classes | Early-closure rule | Notice |
|---|---|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 when closed within 30 days of opening | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 when closed within 60 days of opening | 3 days |
| Premium | Evergreen Account | $50 when closed within 90 days of opening | 7 days |
| Elite | Bluest Account | $100 when closed within 180 days of opening | 14 days |

Use the actual `date_opened` and the current time, not an estimate of account tenure. For an early-closure window, treat the fee as applicable before the relevant opening-date anniversary (`date_opened + window days`).

The balance rule is exact:

- If the early-closure fee applies, the current balance must be at least the fee. The fee is deducted from the account; do not offer an alternative payment method.
- If no early-closure fee applies, the current balance must be exactly $0.

Use `scripts/assess_closure.py` after transcribing the relevant current tool fields into its JSON input. It is a deterministic aid only; it does not query systems or perform a bank action. Its stdin schema is:

```text
{
  "account": {"account_id": string, "account_class": string, "status": string,
              "balance": number-or-string, "date_opened": date-or-timestamp},
  "transactions": [transaction records with at least "status"],
  "debit_cards": [card records with at least "status"],
  "evaluation_time": current timestamp string,
  "notice_given_at": optional timestamp string
}
```

It emits one JSON object containing the normalized tier, fee, notice deadline, blockers, and `can_close`. Treat an `errors` entry, an unknown class, malformed date, or missing required status as a blocker that needs resolution rather than as an eligible result.

## 4. Handle notice correctly

A closure request gives notice only when it is an explicit, verified customer instruction to close the identified account. Record the request timestamp in the permitted case context and calculate the earliest closure time by adding the tier's full notice days. Do not represent a notice as recorded in a banking system if no supported record mechanism exists.

For accounts requiring notice, do not call the account-closure tool before the deadline. Explain the earliest date/time and all other blockers. At or after that time, refresh account, transaction, and debit-card results because eligibility can change. Recalculate the fee based on the then-current date and recheck the balance before closure.

## 5. Close only when every condition passes

Immediately before closing, confirm all of the following from current records:

- verified customer and correct requested account;
- account status is `OPEN`;
- all linked debit cards are `CLOSED` (or there are none);
- no account transaction is pending;
- notice period has elapsed;
- correct balance condition for the current fee outcome.

Then unlock `close_bank_account_7392`. Use only the parameters exposed by that tool's discovered contract; pass the selected account ID if its contract requires an account identifier. Do not invent parameters or retry an operation with an unknown result. Confirm closure to the customer only after a successful tool response. State the fee deducted, if any, and distinguish a completed closure from a pending notice or unmet prerequisite.

## Customer-facing outcome

Give a concise status that identifies the requested account (without exposing unnecessary identifiers), states whether it was closed, and, if not, lists the specific required next steps: amount needed for a fee, balance withdrawal requirement, pending transaction settlement, card closure, or notice deadline. Do not state that an account is closed merely because a request or notice was received.
