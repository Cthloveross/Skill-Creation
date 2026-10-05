---
name: atm-debit-card-decline-triage
description: Diagnose ATM cash-withdrawal declines involving one or more debit cards, including different checking-account tiers or a teen account. Use when a customer needs cash, reports a decline or uncertain ATM error, or asks whether a daily ATM limit can be increased.
---

# ATM Debit-Card Decline Triage

Use this Skill to safely identify the cause of an ATM decline, prioritize the card that can most quickly provide access to cash, and perform only authorized, verified banking actions. It is especially useful when several cards were declined at the same ATM: do not assume all cards share the same cause.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A lookup or calculation does not itself authorize a change. Never perform an action merely because the triage script recommends that it could be considered.

## Inputs to collect

Collect or confirm, without revealing information from records:

- Customer identity and the card/account owner for every card being discussed.
- The exact withdrawal amount, whether it is one cash request or several, the ATM branding/operator, and whether cash was dispensed.
- The exact decline text or code, if available; ask for a photo or receipt only if the customer can do so safely.
- Whether the customer recognizes recent transactions and whether a card is lost, stolen, damaged, frozen, or has had repeated PIN attempts.
- For a minor/teen card, confirmation that the cardholder is present and the appropriate owner/guardian has authority for any requested change.

An absent code is meaningful: describe it as an unspecified decline and do not diagnose it as a particular decline code.

## Identity, ownership, and authority

1. Locate the customer with a supplied identifier if necessary using the normal user lookup tool.
2. Verify at least two independent identity fields out of date of birth, email, phone number, and address by having the customer provide them and comparing them to the record. Do not read fields back as verification prompts.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` using the complete record and that timestamp after successful verification.
4. Confirm the person is the owner of the selected debit card and linked account. For a teen/minor account, determine the cardholder and guardian/primary-account-holder authority separately. Do not alter parental controls or a teen card's settings without the required guardian authorization.
5. If identity, ownership, authority, or required confirmation cannot be established, do not change limits, clear protections, reset a PIN, freeze/unfreeze, or disclose account-specific details. Escalate when the safety concern requires it.

## Retrieve the current facts

After the appropriate verification and authority checks, use the runtime's discoverable-agent workflow: first call `unlock_discoverable_agent_tool`, then call the unlocked tool through `call_discoverable_agent_tool` with JSON arguments.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with `user_id`.
   - Identify checking accounts, their `account_id`, `account_class`, `status`, `balance`, and `date_opened`.
2. For each relevant checking account, unlock and call `get_debit_cards_by_account_id_7823` with `account_id`.
   - Match the physical card with the customer using last four digits and confirm `card_id`, linked account, `status`, issue reason, expiration, and current limit/usage/security fields if returned.
3. Unlock and call `get_bank_account_transactions_9173` for the selected account(s).
   - Inspect pending debits, recent ATM withdrawals, and overdraft-fee history. Transactions are returned newest first.
4. Keep the selected Green, Blue, and teen/Light Green cards separate. A card can have a different status, security protection, daily usage, linked-account status, or ATM limit.

Use `scripts/atm_decline_triage.py` to calculate displayed remaining daily ATM allowance and to identify missing limit-increase prerequisites. The script is advisory and cannot establish available balance, authorization holds, identity, authority, or transaction legitimacy.

## Diagnose in safe order

For the card the customer wants to use first, check the following before suggesting a limit change.

### 1. Card and linked-account status

- If the card is `FROZEN`, offer unfreezing only after identity, ownership, linked-account `OPEN` status, and explicit confirmation. The card must actually be frozen.
- If the card is `CLOSED`, it cannot be used; check for an active replacement or offer the appropriate replacement path.
- If the card is `PENDING`, it needs activation through the applicable activation process.
- If the card is `ACTIVE`, continue.
- If the linked checking account is not `OPEN`, say only that an account restriction is preventing transactions and direct the customer to a branch or the dedicated account-services line. Do not reveal details for suspended or restricted accounts.

### 2. Fraud alerts and velocity blocks

- If a fraud alert is customer-initiated, first verify identity and have the customer confirm that recent transactions are legitimate. Only then, with explicit confirmation, unlock and call `clear_debit_card_fraud_alert_4892` with the matched `card_id` and `reason: "customer_verified"`. Document why it was cleared.
- If a fraud alert is bank-initiated, do not attempt to clear it. Tell the customer that a security flag requires additional review and transfer to the security team with reason `fraud_or_security_concern`.
- If `velocity_blocked` is true, explain that it normally clears after 30 minutes. After identity verification, a reasonable explanation, ownership checks, and explicit confirmation to lift it early, the authorized action is `clear_debit_card_fraud_alert_4892` with `reason: "velocity_clear"`. Document the reason.

If the ATM response indicates an internal fraud-sensitive code (04, 07, 34, or 59), do not disclose the code or fraud rationale. Provide the prescribed generic security/in-person assistance message and transfer or direct to a branch as required.

### 3. PIN state

If the card lookup shows a locked PIN, or the ATM explicitly reports a PIN decline:

- Do not unlock it casually and do not reveal internal fraud-risk calculations.
- Follow the PIN-lock fraud-risk protocol: first check security-hold, other-locked-card, and recently stolen-card escalation triggers; then gather the required card, account, and declined/successful transaction data and apply its scoring, verification, and escalation rules.
- A `security_hold`, another locked card requiring investigation, a recent stolen-card trigger, or an unsafe/high-risk outcome requires the prescribed escalation. Do not invent an unlock tool.
- A PIN reset/change is a separate customer request. It requires verified identity, card ownership, an `ACTIVE` card, correct last four digits or current PIN as applicable, and a compliant new PIN. Never repeat a PIN back.

### 4. Balance and pending activity

A posted balance that appears sufficient is not proof that the ATM request can be authorized. Compare the requested amount with available funds where available, and review:

- Pending debit transactions;
- Recent authorization holds (for example fuel, lodging, rentals, or restaurant tip buffers);
- Recent ATM withdrawals and current daily ATM use;
- POS/ATM overdraft settings where returned.

Explain pending debits and holds factually. Do not claim a hold exists unless it is known or the customer confirms it. If funds are genuinely insufficient, offer a smaller withdrawal or funding/transfer options without executing a transfer unless all banking prerequisites and confirmation requirements are met.

### 5. Limits and ATM/terminal issues

Use live card fields (`daily_atm_limit` and `daily_atm_used`) as the operational facts. The product guidance gives these useful baseline checks:

- Green Account (checking): a $600 daily ATM limit; a $550 request is below the stated product limit before prior withdrawals and other restrictions are considered.
- Blue Account: a $500 daily ATM limit; a $550 request exceeds that stated limit.
- Light Green Account: a $150 daily ATM limit; a $550 request exceeds that stated limit.

For any card, calculate remaining daily allowance as `max(daily_atm_limit - daily_atm_used, 0)`. A request at or below the published limit may still fail if prior withdrawals reduced the remaining allowance, a live card-specific limit differs, the account cannot authorize it, or there is a security/terminal issue.

A non-bank ATM can impose its own lower withdrawal limit; the bank cannot override it. When the issue affects multiple cards at one ATM and no card-specific block is found, avoid repeated attempts at that machine and recommend a different ATM, preferably a bank-branded machine, or another payment arrangement with the tow provider. Do not label the terminal as flagged unless Code 58 or an equivalent terminal finding is actually returned. If a terminal is confirmed flagged, advise a different register/merchant or ATM; if unrelated terminals are also affected, return to the generic card-status/security diagnostic.

For known technical/network outcomes: Code 19 can be retried immediately once; Codes 91/96 warrant retrying in a few minutes and, if persistent, 10–15 minutes; Code 92 warrants a retry or a different merchant/ATM. Unknown decline text does not prove one of these codes.

## Temporary ATM limit increase

Offer this only when the customer requests it, the live card's usable daily ATM limit is the likely constraint, and a different ATM or smaller withdrawal does not resolve the immediate need. Before an action, verify and record all of the following:

1. The linked checking account is `OPEN` and in good standing.
2. The account is at least 60 days old, calculated from `date_opened` to the current date.
3. Transaction history shows no overdraft-fee transaction in the previous 30 days.
4. The selected debit card is `ACTIVE`.
5. No more than one temporary increase has been granted to this card in the prior 24 hours; obtain this fact from the available system record or do not proceed.
6. The requested `new_limit` is no more than 150% of the current limit.
7. The customer explicitly confirms the exact temporary limit, understands it lasts 24 hours, and understands a third-party ATM may still impose a lower cap.

When every requirement is satisfied, unlock and call `request_temporary_debit_card_limit_increase_8374` with:

```json
{"card_id":"<matched card id>","limit_type":"atm","new_limit":<confirmed numeric limit>}
```

Report the tool result exactly and do not promise that a third-party ATM will dispense cash. If any eligibility criterion is unknown or fails, explain which operational requirement prevents the request and offer the safer alternatives above.

## Customer-facing response structure

After the lookups, give a short, urgent but accurate response:

1. State which selected card, if any, is the best next option and why.
2. State the exact verified blocker or explain that the decline remains unspecified.
3. Give one immediate next step: a smaller amount, another ATM, a wait period, security transfer, or a properly confirmed authorized action.
4. State material limits or third-party ATM constraints.
5. Avoid promising cash availability, exposing internal fraud signals, or stating that a limit increase is approved before the action succeeds.

If repeated attempts still fail, capture the ATM/operator, timestamps, screen text, requested amount, and whether cash was dispensed; collect device/app details only when relevant, then escalate with the documented facts if multiple attempts have the same result.

## Advisory script

Run the packaged script through `run_skill_script`:

```json
{
  "relative_path": "scripts/atm_decline_triage.py",
  "input_json": {
    "requested_amount": 0,
    "current_date": "YYYY-MM-DD",
    "cards": [],
    "accounts": [],
    "transactions": []
  }
}
```

Input schema:

- `requested_amount` is a non-negative number.
- `current_date` is `YYYY-MM-DD`.
- Each `cards` object requires `card_id`, `account_id`, `status`, `daily_atm_limit`, and `daily_atm_used`; optional fields include `card_number_last_4`, `account_class`, `fraud_alert_active`, `alert_source`, and `velocity_blocked`.
- Each `accounts` object requires `account_id`, `status`, and `date_opened` (`YYYY-MM-DD` or `MM/DD/YYYY`).
- Each `transactions` object may include `account_id`, `date`, `type`, and `status`.

The script emits JSON with per-card remaining limit, whether the requested amount exceeds that remaining limit, known security-state warnings, and computed temporary-increase prerequisites. `null` or `"unknown"` means more information is required rather than that a requirement passed. Validate that every selected `card_id` maps to a returned account, amounts are non-negative, dates parse, and the script has not converted unknown data into eligibility.
