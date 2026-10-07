---
name: pin-lock-fraud-investigation
description: Investigate one or more debit cards reported PIN-locked or declined for PIN reasons. Use before any PIN unlock decision to collect account/card/transaction evidence, apply the required fraud-risk protocol, verify the customer, and escalate or reset/replace safely when required.
---

# PIN-lock fraud investigation

Use this Skill when a customer reports a PIN lock, incorrect-PIN decline (including decline codes 55 or 75), or several debit cards locked at once. Do **not** simply unlock a PIN-locked card. Do not disclose fraud-score calculations, individual flags, internal codes, or security rationale to the customer.

## Safety and prerequisites

1. Identify the customer and retrieve **all** of their accounts and debit cards. Confirm which cards are affected; do not infer a particular card from an account nickname or balance.
2. Before changing a PIN, clearing a security protection, or using any unlock capability, verify identity by having the customer confirm two of date of birth, email, phone, and address. Obtain the current timestamp and call `log_verification` with the verified record.
3. Assess every locked card individually. If another card on the same account is also PIN-locked, finish the investigations for all such cards before unlocking any of them.
4. Treat missing risk evidence as unknown, not zero. Ask the customer for the missing relevant information and use only returned tool data. If a required safety decision cannot be supported, escalate to the security team rather than guessing.
5. Never use `reset_debit_card_pin_6284` as an implicit unlock. A reset requires the documented verified-owner, ACTIVE-card, confirmed-last-four, and valid-new-PIN prerequisites, and the customer must agree to reset.

## Retrieve evidence

The documented specialist tools must first be made available through `unlock_discoverable_agent_tool`, then called with `call_discoverable_agent_tool`:

- `get_all_user_accounts_by_user_id_3847(user_id)` for checking account IDs, status, balance, and opening date.
- `get_debit_cards_by_account_id_7823(account_id)` for every card on each checking account.
- `get_bank_account_transactions_9173(account_id)` for transaction history.

Capture actual returned fields only. The published transaction schema does not enumerate declined ATM/POS records and the published card schema does not enumerate PIN-lock, lock-reason, fraud-alert, or velocity fields. If the live response supplies such fields, use them; otherwise do not fabricate them or treat their absence as a clear result. Ask for the ATM/merchant location, approximate time, amounts, and whether attempts were the customer's when needed.

For each investigated card, record internally: card ID, last four, status, date issued, ATM limit, PIN-lock state/reason (if returned), prior PIN locks during 90 days (if available), all recent declined PIN attempts, recent successful PIN/ATM activity, other-card security states, account opening date/balance, overdraft fees, and any stolen-card replacements issued within 90 days.

## Required decision order

### 1. Automatic triggers

Before scoring each card, check the following:

- `pin_lock_reason == security_hold`: do not unlock; offer a security-team transfer.
- Any other card on that account is PIN-locked: investigate every locked card first; defer all unlocks until they are complete.
- Any card on the account was issued in the last 90 days with `issue_reason == stolen`: require enhanced verification before an otherwise eligible unlock.

A bank-initiated fraud alert cannot be cleared by an agent and requires security transfer. A customer-initiated alert or velocity block may be cleared only after identity verification and only with `clear_debit_card_fraud_alert_4892` using its documented reason. That tool is not a PIN-unlock tool.

### 2. Risk assessment

Normalize collected evidence and run the packaged calculator:

```text
python3 scripts/score_pin_lock_risk.py <<'JSON'
{"home_location":{"city":"...","state":"...","country":"US"},"declines":[...],"now":"..."}
JSON
```

The script reads one JSON object from stdin and writes one JSON result to stdout. Its full input schema is in `references/risk_input_schema.md`. Its output includes internal `flags`, `total_score`, `missing_inputs`, `automatic_triggers`, and a preliminary protocol. Do not show that output to the customer.

The calculator scores each named flag once, using the most risk-indicating applicable observation where the protocol supplies multiple attempts (and uses the required aggregate for daily-limit total). Review its `assumptions` and `missing_inputs`; replace uncertain values with verified facts rather than assuming them.

Apply the protocol:

- 0–4: low risk — unlock only after standard identity verification.
- 5–7: medium risk — ask exactly: “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after the required answer and verification support it.
- 8–10: high risk — ask about the flagged location and time. Unlock only if the customer confirms and gives a satisfactory explanation.
- 11–14: very high risk — do not unlock on this contact; require callback verification or enhanced verification (last four SSN plus a security question).
- 15+: critical — do not unlock; check for successful unauthorized activity and recommend closure/replacement.
- Any single 3-point flag requires supervisor review regardless of total. Three or more prior locks in 90 days requires a PIN reset rather than unlock.

For totals of 5 or higher, ask only the prescribed flag-specific questions when applicable:

- Location: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” If yes, remove location flags and recalculate.
- Decreasing amount pattern: “The attempts were for [amounts]. Do you remember trying those specific amounts?” If confirmed, remove only the amount-pattern flag and recalculate.
- Time-of-day score 2 or 3: “These attempts occurred at [time]. Were you trying to use your card at that time?” If confirmed, remove that time flag and recalculate. If the customer says they were asleep or gives an equivalent denial, treat this as critical suspected fraud; do not unlock.

Supply confirmed answers in `confirmations` and rerun the calculator to retain an internal audit of the recalculation.

### 3. Execute only a supported outcome

Use an actual PIN-unlock capability only if it is explicitly available in the declared runtime and all the above conditions permit unlocking. Do not invent a tool name or substitute another card action. If no documented/available unlock capability exists, explain that further security review is needed and transfer to a human security specialist.

After an eligible unlock, comply with lock-history follow-up:

- 0 prior locks: normal completion.
- 1 prior lock: offer PIN-lock notifications.
- 2 prior locks: offer a PIN reset because this is the third lock in 90 days.
- 3+ prior locks: do not unlock; complete an agreed, valid PIN-reset workflow or escalate as needed.

When the outcome is no unlock, examine the suspicious period for successful transactions the customer says are unauthorized. If found, follow the required dispute/closure/replacement process. If none are found, explain only that a security review is needed and offer security investigation, PIN reset, or card replacement as appropriate. Transfer with `transfer_to_human_agents` using `fraud_or_security_concern` when fraud/security review or supervisor review is required, including a concise internal summary of evidence, verification state, and actions not taken.

## Customer communication

Acknowledge urgency without promising access. State only the next needed verification or investigation step. Never reveal scores, calculations, fraud codes, unverified transaction details, PIN values, full card numbers, or whether a particular security control was bank-initiated. Do not claim a card is unlocked, reset, disputed, closed, or replaced unless the corresponding supported bank action actually succeeded.
