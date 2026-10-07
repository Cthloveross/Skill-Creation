---
name: debit-card-decline-investigation
description: Investigate a Rho-Bank debit-card purchase decline using account, card, and transaction evidence. Use for an unexplained in-person, online, or ATM decline, especially when a decline code is unavailable. It supports safe diagnosis of card status, account restrictions, balance/pending activity, fraud alerts, velocity blocks, PIN locks, and card limits without taking unverified or prohibited security actions.
---

# Debit-card decline investigation

## Scope and safety boundaries

Use this Skill to diagnose a decline and explain the next appropriate step. Read-only investigation may proceed using the customer's resolved profile and linked account/card records. Do **not** change card controls, clear alerts or blocks, activate, freeze, close, unlock, or increase a limit merely because a decline occurred.

A name or account lookup is identification, not identity verification. Before any state-changing card action, verify the customer using two of the four required identity fields (date of birth, email, phone number, address), obtain the current timestamp, and log the verification using the normal banking tools. Also apply every action-specific prerequisite in the applicable procedure.

Do not disclose internal fraud decline codes or a suspected-fraud rationale to a customer. Do not attempt to clear a bank-initiated fraud alert. Do not simplify or bypass the PIN Lock Investigation Protocol when `pin_locked` is true.

## Runtime inputs

At runtime, collect the actual conversation and read-only observations; do not reuse identifiers or facts from another case.

Required investigation data, when available:

- Resolved `user_id` and linked checking-account record(s), including account status, balance/available balance, account age, account class, and POS-overdraft setting.
- All debit cards linked to the relevant checking account, including status, issue reason, dates, limits and usage, fraud/velocity/PIN fields, restrictions, and geographic controls.
- Recent account transactions, including pending items, authorization holds if exposed, successful activity, decline records, amounts, locations, and timestamps.
- The customer's channel, approximate amount, whether a PIN was entered, any notification/decline code, and recent hold-producing activity.

Use normal runtime read tools to resolve the customer's linked checking account and recent activity. When a documented specialized tool is required, unlock it first and then call it exactly as documented. Relevant documented tools include:

- `get_debit_cards_by_account_id_7823(account_id)` for all debit cards tied to a checking account.
- `get_bank_account_transactions_9173` when transaction history is needed and that documented tool is available in the runtime.
- `clear_debit_card_fraud_alert_4892(card_id, reason)` only after the required verification and only for an eligible customer-initiated alert or velocity block.
- `request_temporary_debit_card_limit_increase_8374(card_id, limit_type, new_limit)` only if the customer requests it and all eligibility checks pass.

Never invent a tool name or parameters that are absent from the runtime or supplied procedure.

## Investigation workflow

1. **Clarify only the missing facts needed for diagnosis.** Confirm transaction channel, whether a PIN was entered (a chip insertion alone does not establish this), approximate amount, decline code/message, and recent gas, hotel, rental, large-purchase, or other authorization holds. If the customer does not know, continue with records rather than treating the lack of a code as evidence.
2. **Resolve the correct checking account and card.** Retrieve linked checking account data and all cards for the account. If multiple possible active cards exist, match the customer-provided last four digits or ask a minimal clarifying question. Do not expose full card data.
3. **Retrieve recent activity.** Review pending debits, recent holds, declined attempts, and successful activity relevant to the time of the decline. Distinguish posted balance from available funds; a posted balance alone cannot establish that sufficient funds were available.
4. **Run the deterministic triage helper.** Supply the collected, normalized observations to `scripts/analyze_decline.py`. Treat its output as a checklist and calculation aid, not authority to perform an action.
5. **Apply the evidence-specific procedure.** Explain only supported findings and the customer-safe remedy. If the helper reports missing information, obtain it or state the diagnosis remains incomplete.
6. **Only then perform a requested eligible action.** Obtain verification and consent where required, recheck current status immediately before the action, use the documented banking tool, and report the actual tool result. A recommendation produced by the script never performs a banking action.

## Required decision rules

### Generic / Code 05 diagnostic order

For a generic decline or no code, inspect in this order:

1. **Card status:** FROZEN (ask whether the customer wants it unfrozen and follow the unfreeze procedure), CLOSED (explain it is inactive and check for a replacement/another active card), PENDING (activation workflow), or ACTIVE (continue).
2. **Linked account status:** if not OPEN, do not disclose details for SUSPENDED or RESTRICTED accounts. Use the approved restriction message: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
3. **Fraud alert:** customer-initiated alerts can be cleared only after verification and confirmation that recent transactions are legitimate. Bank-initiated alerts must be transferred to the security team; never clear them.
4. **Velocity block:** explain that it normally lifts after 30 minutes. An early clear requires identity verification and `velocity_clear` through the documented clearing tool.

For an unknown decline, also assess balance/holds/pending debits, purchase limits, applicable card restrictions, and PIN status. Do not claim that a particular cause applies unless record evidence supports it.

### Balance and limits

For apparent insufficient funds, compare the requested amount with **available** funds, pending debits, and authorization holds. Explain that pending holds commonly release in 1–3 business days when that is the relevant supported finding. If funds are truly insufficient, offer adding/transferring funds or a smaller purchase.

For a purchase or ATM limit, calculate remaining capacity as `daily_limit - amount_used_today`; do not allow a negative remaining value. A temporary increase requires an OPEN account, account age of at least 60 days, no overdraft fees in the past 30 days, an ACTIVE card, no other temporary increase in the prior 24 hours, customer request, and a requested limit no greater than 150% of the current limit. Third-party ATM limits cannot be overridden.

### PIN and security cases

- For Code 55 or 75, or any `pin_locked = true`, conduct the complete PIN Lock Investigation Protocol before any unlock. Check automatic escalation triggers first, score the required transaction/card/account factors from actual data, apply the single-three-point escalation rule, ask required risk questions, and follow the score threshold. Do not reveal internal scoring calculations.
- For Code 83, explain it is a temporary PIN-verification network problem, not proof of a wrong PIN; retrying, a signature transaction where permitted, another terminal, or waiting 10–15 minutes are appropriate.
- Code 04, 07, 34, or 59 must not be disclosed. Give only the approved branch/in-person verification response and transfer if pressed.
- For a reported stolen-card situation or a bank-initiated security flag, follow the security escalation path rather than unfreezing/reactivating.

## Interpreting helper output

Run:

```text
python3 scripts/analyze_decline.py <<'JSON'
{
  "accounts": [{"account_id": "...", "status": "OPEN", "available_balance": "0.00"}],
  "cards": [{"card_id": "...", "account_id": "...", "status": "ACTIVE"}],
  "transactions": [],
  "decline": {"account_id": "...", "card_id": "...", "channel": "in_person", "amount": "0.00", "code": null},
  "identity_verified": false
}
JSON
```

The program reads one JSON object from stdin and emits one JSON object to stdout. All IDs and values above are placeholders. Its output contains `findings`, `missing_data`, `customer_safe_next_steps`, and `action_gates`. Review these against the live records and procedures before speaking or acting.

Validation expectations: output must be valid JSON; `findings` must be evidence-linked; unavailable fields must appear in `missing_data` instead of being assumed; and `action_gates` must remain blocked when `identity_verified` is false or a documented prerequisite is absent.

## Completion

Tell the customer the evidence-supported cause or, if unresolved, the specific remaining check. Give the practical next step (for example, retry after a velocity block expires, add funds, activate a pending replacement, use another terminal, or contact security). State any completed action only after its banking-tool response confirms success. Record required verification and the reason for any cleared protection in the normal interaction notes.
