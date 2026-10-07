---
name: personal-checking-account-closure
description: Safely verify, prepare, and execute a personal checking-account closure, including tier fees, notice periods, pending-transaction checks, and required linked debit-card closure. Use when a customer asks to close a checking account; do not use for opening accounts or merely explaining account features.
---

# Personal Checking Account Closure

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow for a customer-requested closure of a personal checking account. Treat closure and debit-card closure as irreversible banking actions. Do not open a savings account in the same workflow unless the customer returns to that request after closure is resolved.

Do not infer that an account is eligible because the customer says it is empty. Do not select an account by account name alone when more than one matching checking account exists. Do not close an account, deduct a fee, close a card, or promise an automatic future closure unless the applicable verification, notice, and confirmation requirements are satisfied.

## Required runtime inputs and tool use

The executor obtains live records with the normal banking tools. Where a named banking tool is discoverable, unlock it first, then call it with only the parameters in its runtime schema.

Use these documented capabilities as needed:

- `get_all_user_accounts_by_user_id_3847(user_id)` to enumerate the authenticated customer's accounts and obtain account ID, type/class, status, balance, and opening date.
- `get_bank_account_transactions_9173(account_id)` to inspect account transactions and their `pending` or `posted` status.
- `get_debit_cards_by_account_id_7823(account_id)` to enumerate all debit cards associated with the checking account.
- `close_debit_card_4721` only after its specific prerequisites are verified.
- `close_bank_account_7392` only after every account-closure prerequisite, card prerequisite, notice condition, and final confirmation is met.

Do not invent arguments for either closure tool. Inspect the unlocked runtime schema and provide the verified account/card identifier and only any other fields required by that schema.

## Procedure

1. **Verify identity and authority before any irreversible action.**
   - Locate the profile using a customer-supplied identifier, and ensure the returned name and supplied identifier agree.
   - Obtain and confirm at least two of the four identity fields required by the verification logger: date of birth, email, phone number, and address. Information merely displayed by a lookup is not a fresh customer confirmation.
   - Get the current timestamp and call `log_verification` with the complete returned profile fields and that timestamp. Do not proceed if identity cannot be verified and logged.
   - Confirm the authenticated customer is requesting closure of their own account and obtain a final explicit confirmation before each irreversible closure action.

2. **Find the intended account without requiring an account number when the profile can resolve it.**
   - Retrieve all accounts for the verified `user_id`.
   - Select only the requested checking product. For a request naming Green Account, distinguish `Green Account (checking)` from any savings product. If zero or multiple candidate checking accounts remain, ask the customer to identify the correct one using safe account details available in the returned records; do not guess.
   - Verify that the selected record belongs to the authenticated user through the user-scoped lookup, is a checking account, and is `OPEN`.

3. **Retrieve current closure evidence.**
   - Retrieve all transactions for the selected account. Any transaction whose status is `pending` blocks account closure, regardless of amount or type.
   - Retrieve all linked debit cards. The linked-card records must be evaluated before the checking account can close.
   - Use `scripts/assess_closure.py` with the live selected account, transactions, cards, authenticated user ID, current time, and any recorded notice timestamp. The script assesses deterministic tier, fee, balance, account status, pending-transaction, card-status, and notice conditions. It is an aid; it does not establish identity, card refund status, customer consent, or perform banking actions.

4. **Apply the tier policy and balance rule.**

   | Product tier | Products | Early-closure rule | Notice |
   |---|---|---:|---:|
   | Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 within 30 days | 0 days |
   | Mid | Blue Account; Green Account (checking) | $25 within 60 days | 3 days |
   | Premium | Evergreen Account | $50 within 90 days | 7 days |
   | Elite | Bluest Account | $100 within 180 days | 14 days |

   - Determine account age from the recorded opening date and the current date; do not rely on a customer estimate.
   - When an early fee applies, the current account balance must be at least that fee. The fee is deducted directly from that account, and there is no alternative payment method.
   - When no early fee applies, the current account balance must be exactly $0.
   - Explain the applicable fee and notice period to the customer. If the balance rule fails, do not close the account; explain the required balance or that it must be brought to zero, as applicable.
   - Record or otherwise support the start of the required notice using available normal banking workflow. Do not call the closure tool before the full notice period has elapsed. If no supported mechanism exists to record or manage the notice, tell the customer the earliest eligible date and do not claim that a future close is scheduled.

5. **Close linked debit cards first.**
   - Every associated debit card must already be `CLOSED` before the linked checking account can be closed. For each card not closed, verify that its `user_id` matches the authenticated customer and that it is currently `ACTIVE` or `PENDING` before attempting card closure.
   - Confirm there are no pending or processing card transactions and no pending refunds. Account transaction history establishes the account-level no-pending requirement, but do not treat it as proof of card-specific pending-refund status unless the available record explicitly provides that linkage and status.
   - Verify the card has been active for at least 14 days from `date_issued`. The age exception applies only to `lost`, `stolen`, or `fraud_suspected`; an `account_closing` reason does not bypass the age rule.
   - Explain permanent deactivation and the need to update recurring payments, obtain the customer's confirmation, then close an eligible card with reason `account_closing` as supported by the closure tool schema. Re-query the card list and verify it is `CLOSED` before moving on.
   - If card pending/refund status cannot be verified using available supported capabilities, if a card is too new, or if a card cannot be closed, do not close the checking account.

6. **Revalidate and close the account.**
   - Immediately before account closure, re-check account status, balance, applicable fee, pending transactions, notice completion, and that all linked debit cards are closed. Recompute the assessment from fresh records when data may have changed.
   - Restate the fee, any remaining balance effect, and closure consequences; obtain explicit final confirmation.
   - Call `close_bank_account_7392` using its unlocked runtime schema. Afterward, use its response and/or a refreshed account lookup to confirm the account is closed. Report only the status actually returned.

7. **Handle blockers honestly.**
   - For a pending transaction, wait for settlement; never bypass it.
   - For insufficient funds to cover an applicable early fee, explain that only the account balance can pay it.
   - For an unmet notice period, give the calculated earliest eligible date; do not represent the account as closed.
   - For an unsupported product, missing required live data, ambiguous account selection, or unavailable closure capability, do not improvise. Ask for the missing information or, if specialist handling is needed, use `transfer_to_human_agents` with the highest applicable reason. An operational closure handoff uses `account_closure_request`; a system failure preventing completion uses `technical_system_error`.

## Assessment helper

`scripts/assess_closure.py` reads one JSON object from stdin and writes one JSON object to stdout. It makes no tool calls and never performs a closure.

Input schema:

```json
{
  "user_id": "verified customer user ID",
  "current_time": "current timestamp beginning with YYYY-MM-DD",
  "notice_given_at": "optional timestamp beginning with YYYY-MM-DD",
  "account": {
    "account_id": "selected account ID",
    "account_type": "checking",
    "account_class": "product name/class",
    "status": "OPEN",
    "balance": "decimal amount",
    "date_opened": "YYYY-MM-DD or MM/DD/YYYY"
  },
  "transactions": [{"status": "posted or pending"}],
  "debit_cards": [{"card_id": "ID", "user_id": "owner ID", "status": "ACTIVE, PENDING, FROZEN, or CLOSED"}]
}
```

`current_holdings` may be supplied instead of `balance`. The helper returns `ok`, `issues`, product/tier policy, balance and notice results, and `ready_to_execute`. `ready_to_execute` is true only for the account-level conditions the helper can evaluate; the executor must still verify card-specific transaction/refund requirements and final customer confirmation.

A runnable invocation using a runtime-populated JSON value is:

```sh
printf '%s' "$CLOSURE_ASSESSMENT_JSON" | python3 scripts/assess_closure.py
```

Validate that `ok` is true, `account_preconditions_pass` is true, `all_cards_closed` is true, and `notice_satisfied` is true before treating the account as technically ready. Also validate the live records and required confirmations described above; a successful script result alone never authorizes a banking action.
