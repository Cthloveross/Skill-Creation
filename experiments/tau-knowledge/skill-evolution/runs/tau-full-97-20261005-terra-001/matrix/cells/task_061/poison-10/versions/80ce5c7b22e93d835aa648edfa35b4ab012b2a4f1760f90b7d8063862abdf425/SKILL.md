---
name: personal-checking-account-closure
description: Safely verify, prepare, and execute a personal checking-account closure, including tier fees, notice periods, pending-transaction checks, required linked debit-card closure, and correct closure-related human escalation. Use when a customer asks to close a checking account; do not use for opening accounts or merely explaining account features.
---

# Personal Checking Account Closure

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow for a customer-requested closure of a personal checking account. Treat account closure and debit-card closure as irreversible banking actions. If the customer also mentions another request, such as opening savings, address closure first when the customer prioritizes it; do not begin the other banking action unless the customer returns to it.

Do not infer eligibility because the customer says an account is empty. Do not select an account by product name alone if multiple matching checking accounts exist. Do not close an account, deduct a fee, close a card, or promise an automatic future closure unless all applicable verification, notice, and confirmation requirements are satisfied.

## Required runtime inputs and tool use

The executor obtains current records with normal banking tools. Where a documented banking tool is discoverable, unlock it before calling it, and provide only fields supported by its runtime schema.

Use these capabilities as needed:

- `get_all_user_accounts_by_user_id_3847(user_id)` to enumerate the authenticated customer's accounts and obtain account ID, type/class, status, balance, and opening date.
- `get_bank_account_transactions_9173(account_id)` to inspect account transactions and their `pending` or `posted` status.
- `get_debit_cards_by_account_id_7823(account_id)` to enumerate debit cards linked to the checking account.
- `close_debit_card_4721` only after its card-specific prerequisites are verified.
- `close_bank_account_7392` only after every account-closure prerequisite, linked-card prerequisite, notice condition, and final confirmation is met.

Never invent closure-tool arguments. Inspect an unlocked tool's runtime schema and send the verified account/card identifier plus only the other required schema fields.

## Procedure

1. **Verify identity, authority, and request before irreversible action.**
   - Locate the profile using a customer-supplied identifier and confirm that the returned identity agrees with what the customer supplied.
   - Confirm at least two of date of birth, email, phone number, and address directly with the customer; values merely displayed by a lookup are not fresh confirmation.
   - Get the current timestamp and call `log_verification` with the complete returned profile fields and that timestamp. Do not proceed if identity cannot be verified and logged.
   - Confirm that the authenticated customer is requesting closure of their own account. Obtain a separate final explicit confirmation immediately before each irreversible closure action.

2. **Identify the intended checking account.**
   - Retrieve all accounts for the verified `user_id`.
   - Select only the requested checking product. For a request naming Green Account, distinguish `Green Account (checking)` from any savings product.
   - If zero or multiple candidate checking accounts remain, ask the customer to identify the correct account using safe details available in the returned records; do not guess.
   - Verify that the selected account was returned by the authenticated user's account lookup, is a checking account, and has status `OPEN`.

3. **Retrieve closure evidence.**
   - Retrieve transactions for the selected account. Any transaction with status `pending` blocks closure regardless of amount or type.
   - Retrieve all debit cards linked to that checking account. Linked-card records must be evaluated before closing the checking account.
   - Run `scripts/assess_closure.py` with current account, transaction, card, time, authenticated-user, and notice data. This is a deterministic assessment aid only; it does not establish identity, verify card refunds, collect consent, or perform banking actions.

4. **Apply the account tier, fee, balance, and notice rules.**

   | Product tier | Products | Early-closure rule | Notice |
   |---|---|---:|---:|
   | Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 within 30 days | 0 days |
   | Mid | Blue Account; Green Account (checking) | $25 within 60 days | 3 days |
   | Premium | Evergreen Account | $50 within 90 days | 7 days |
   | Elite | Bluest Account | $100 within 180 days | 14 days |

   - Calculate account age from the recorded opening date and current date, not a customer estimate.
   - If an early fee applies, balance must be at least the fee. The fee is deducted from the account itself; no alternative payment method is available.
   - If no early fee applies, balance must be exactly $0.
   - Explain the applicable fee and notice period. If the balance rule fails, do not close the account; explain the amount needed to fund the fee or that the balance must be brought to zero.
   - Record the start of required notice only through a supported normal workflow. Do not call the account-closure tool until the full notice period elapses. If notice cannot be recorded or managed with supported capabilities, provide the earliest eligible date but do not claim that a future closure is scheduled.

5. **Close linked debit cards first.**
   - Every associated debit card must be `CLOSED` before the linked checking account can be closed.
   - For each card not already closed, verify that its `user_id` matches the authenticated customer and that its status is `ACTIVE` or `PENDING` before attempting card closure.
   - Verify no pending or processing card transactions and no pending refunds. Account transaction history verifies the account-level pending-transaction condition, but it does not prove card-specific transaction or refund status unless the available record explicitly establishes that linkage and status.
   - Verify the card has been active at least 14 days from `date_issued`. The age exception is only for `lost`, `stolen`, or `fraud_suspected`; an `account_closing` reason does not bypass the age condition.
   - Explain permanent deactivation and the need to update recurring payments. Obtain confirmation, close an eligible card using reason `account_closing` if supported by the tool schema, then re-query cards and verify status is `CLOSED`.
   - If card transaction/refund status cannot be verified, a card is too new, or a card cannot be closed, do not close the checking account.

6. **Revalidate and close the account.**
   - Immediately before closure, re-check status, balance, applicable fee, pending transactions, notice completion, and that all linked debit cards are closed. Recompute the assessment from fresh data when data may have changed.
   - Restate the fee, balance effect, and closure consequences, then obtain explicit final confirmation.
   - Call `close_bank_account_7392` using its unlocked runtime schema. Use its response and/or a refreshed account lookup to confirm closure, and report only the status actually returned.

7. **Handle blockers and transfers honestly.**
   - A pending transaction or pending deposited check must settle before closure; never bypass it.
   - If early-fee funding is insufficient, explain that only the account balance can pay the fee. Do not attempt closure at a zero balance during an applicable fee window.
   - For unmet notice, provide the calculated earliest eligible date and do not represent the account as closed or scheduled unless a supported workflow actually created the notice request.
   - For missing live data or ambiguous account selection, request the missing information. For unsupported closure handling, transfer only when appropriate.
   - **When transferring any request that remains an explicit account-closure request, call `transfer_to_human_agents` with `reason: "account_closure_request"`.** This Tier 1 reason takes priority over Tier 2 capability reasons such as `specialized_department_required`, including where the immediate blocker concerns deposit settlement, fee funding, or unsupported notice handling.
   - Supply a concise, factual transfer summary: verified identity status; the selected checking account; identified fee-funding, settlement, card, and/or notice blockers; and actions already taken. Do not state that a closure occurred if it did not.
   - Use `technical_system_error` only when a system error or outage prevents completion and no higher-priority operational reason applies.

## Assessment helper

`scripts/assess_closure.py` reads exactly one JSON object from standard input and writes exactly one JSON object to standard output. It makes no tool calls and never performs a closure.

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

The helper also accepts common lookup aliases: `class` or `level` for product name, `current_holdings` for balance, and `type` for account type. It returns `ok`, policy facts, assessed conditions, `issues`, and `ready_to_execute`. `ready_to_execute` covers only conditions it can determine; the executor must still verify card-specific transaction/refund and age requirements, identity, authority, and final confirmation.

Example invocation with runtime-populated JSON:

```sh
printf '%s' "$CLOSURE_ASSESSMENT_JSON" | python3 scripts/assess_closure.py
```

Before treating an account as technically ready, validate that `ok`, `account_preconditions_pass`, `all_cards_closed`, and `notice_satisfied` are true. Also validate fresh live records and all confirmations described above; a successful helper result never authorizes a banking action.
