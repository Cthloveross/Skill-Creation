---
name: pin-lock-investigation
version: 1.0.0
description: Investigate one or more PIN-locked debit cards before any PIN-unlock decision. Use for debit-card PIN declines/locks, especially when several cards are affected. It inventories all cards, checks mandatory escalation triggers, gathers the records needed for a non-disclosed fraud-risk assessment, and directs the appropriate verification, reset, dispute, or security-team path.
---

# PIN-lock investigation

## Safety and scope

A PIN lock is **not** a fraud-alert or velocity-block clearance. Never use a fraud-alert/velocity tool as a substitute for a PIN-unlock decision. Do not tell a customer the internal score, flag names, formulas, security-hold reason, or decline code.

Do not claim a PIN was unlocked unless an explicitly supplied, authorized PIN-unlock action has actually succeeded. The supplied documentation names no PIN-unlock tool. If no such normal banking tool is available, complete the investigation and use the required escalation/reset path rather than inventing an action or tool.

Treat a customer name, email, or account/card last four as an identifier, not identity verification. Before a reset, alert clearance, dispute, closure, or any other account-changing action, obtain and validate two of the four standard fields (DOB, email, phone, address), obtain the current timestamp, and call `log_verification` with the verified profile values. Do not reveal profile values to help the customer guess them.

## Runtime inputs and available records

Use the live conversation and existing tool observations as facts; do not re-ask questions already answered. The customer may not know card numbers, times, or ATM locations. That is not a reason to assume the attempts were legitimate.

To locate data, first identify the user from a customer-provided identifier. Then, when the named tools are available as discoverable internal tools, unlock and call these documented tools:

1. `get_all_user_accounts_by_user_id_3847(user_id)` to inventory accounts, balances, status, and opening dates.
2. For every checking account, `get_debit_cards_by_account_id_7823(account_id)` to inventory current and historical cards, including PIN/security fields when returned.
3. `get_bank_account_transactions_9173(account_id)` for every checking account that has a relevant card. Preserve transaction IDs, dates, descriptions, amounts, types, and statuses.

The PIN-lock protocol requires declined `atm_withdrawal_declined` and `pos_declined` records, even if a general transaction-tool reference omits them. Use such records if returned by the live system. If essential fields or decline records are not available, record the gap and do not manufacture a low score. For a multi-card lock or other suspicious situation that cannot be assessed, transfer to the security team.

If a named internal tool cannot be unlocked or returns an error, do not retry a potentially state-changing action. Explain only that the investigation needs specialist review and transfer with `fraud_or_security_concern` when the missing information prevents the mandated assessment.

## End-to-end procedure

### 1. Inventory before deciding anything

1. Match any account nickname/class supplied by the customer (for example, “main” or an account name) against the retrieved accounts. If it is ambiguous, ask the customer for a last four digit or a non-sensitive account identifier.
2. Inspect **all** checking-account debit cards, not only the first card named. Identify cards with `pin_locked = TRUE`; keep closed/historical cards because they can establish stolen-replacement and card-history triggers.
3. A report that several cards locked requires each locked card to be assessed independently. Do not unlock any card until investigation of every locked card is complete.
4. Check automatic triggers for each card:
   - `pin_lock_reason == "security_hold"`: chat must not unlock that card; offer/perform security-team transfer.
   - any other card on the same account is PIN-locked: finish all relevant card investigations first.
   - a card replaced/issued in the last 90 days with `issue_reason == "stolen"`: require enhanced verification.
5. Check card/account status as well. A PIN reset requires the card to be ACTIVE and owned by the verified customer. Do not treat an inactive card as reset eligible.

### 2. Normalize evidence and calculate risk privately

For each PIN-locked card, gather and normalize:

- customer home city/state/country from address;
- each relevant decline: timestamp, city/state/country, amount, and chronological order;
- successful transactions in the seven preceding days and whether they are all in the home city;
- last successful PIN use timestamp;
- successful recent ATM withdrawals for the historical ATM average;
- card daily ATM limit, issue date, and prior PIN-lock count in 90 days;
- other cards’ velocity blocks and fraud alerts;
- account opening date, current balance, and recent overdraft fees.

Use `scripts/score_pin_lock.py` only with normalized factual inputs. It emits internal flags, gaps, automatic triggers, total, and routing. Do not show its output to the customer. Review `gaps`: a score is decision-ready only when the necessary fields are present. Do not silently score missing evidence as zero.

Interpret each category once per card using the protocol’s applicable/worst observed evidence: greatest location mismatch, number of distinct decline locations, applicable home-city travel conflict, highest time-of-day band, elapsed time since legitimate PIN use, shortest failed-attempt interval, decline sequence amount pattern, all-round-hundreds check, largest attempted amount against ATM average, combined attempts against daily limit, and card/account history values. Count transaction locations by normalized city/state/country. Use absolute debit amounts.

The helper implements these protocol conditions:

- 0–4 low: standard verification before an otherwise authorized unlock.
- 5–7 medium: after verification, ask exactly: “I see failed PIN attempts on your card. Were those attempts yours?”
- 8–10 high: ask the applicable specific location, amount-sequence, and 2+ point time questions, then recalculate only flags the customer’s clear confirmation permits removal.
- 11–14 very high: no unlock in this interaction; require callback or enhanced verification. If the supported environment cannot complete that path, transfer to security.
- 15+ critical: no unlock; investigate successful unauthorized activity and recommend closure/replacement.
- Any 3-point flag requires supervisor/security review regardless of total. Three or more prior locks in 90 days means no unlock; a PIN reset is required instead.

### 3. Customer questions and recalculation

For score 5+, ask only questions tied to flags present and avoid leading language:

- Location: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” A clear yes removes the location flags and requires recalculation; no/uncertain leaves them.
- Decreasing amounts: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” Confirmation removes only the amount-pattern flag.
- A 2- or 3-point time flag: “These attempts occurred at [time]. Were you trying to use your card at that time?” If the customer says they were asleep or otherwise clearly denies it, treat as likely fraud: do not unlock and transfer/security-escalate.

Keep an audit-quality record of what was asked and the customer response, but do not disclose numerical scoring. A vague answer such as “I’m not sure” does not remove a flag.

### 4. Cannot-unlock, fraud, and reset paths

When an automatic trigger, a 3-point flag, very-high/critical result, unresolved required evidence, or denial indicates no chat unlock:

1. Review the suspicious period for successful transactions. Ask whether any are unauthorized; do not characterize ordinary transactions as unauthorized without customer confirmation.
2. If unauthorized successful transactions are confirmed, use the debit-card dispute procedure only after all of its required Reg E questions and eligibility checks are completed. Select the required category/card action, then separately perform the indicated card action only through an explicitly supplied tool. Physical-card fraud generally requires closure/reissue; do not use an alert-clearing tool instead.
3. If no unauthorized success is identified, explain that additional security review is needed without exposing the internal rationale. Offer PIN reset where permitted, closure/replacement if fraud is suspected, or transfer to security. Use `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise factual summary when specialist review is required.

For a mandatory or customer-requested PIN reset, first meet reset prerequisites: verified owner, ACTIVE card, confirmed last four, and a customer-selected new PIN. Validate that it is exactly four digits, not sequential ascending/descending, not all one digit, and not a birth year or birth month/day. Then, if available, unlock and call `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)`. Never read the PIN back. Confirm only successful completion.

After any legitimate eligible unlock (only if an authorized action exists and succeeds), follow the lock-frequency follow-up: no extra step for zero prior locks; offer PIN-lock notifications for one prior lock; for two prior locks offer PIN reset; for three or more, reset rather than unlock.

## Helper script

`python3 scripts/score_pin_lock.py` reads one JSON object from stdin and emits one JSON object to stdout. It has no network or bank side effects.

Required decision inputs are `as_of`, `card`, `account`, `all_account_cards`, and `home`. Use ISO-8601 timestamps/dates. The full schema and a generic runnable invocation are in the script docstring. Supply empty arrays only when the corresponding dataset was actually checked and found empty; omit unknown fields so they appear in `gaps`.

Example invocation (placeholder data only):

```sh
printf '%s' '{"as_of":"2025-01-01T12:00:00-05:00","home":{"city":"Exampletown","state":"EX","country":"US"},"card":{"date_issued":"2023-01-01","daily_atm_limit":500,"prior_pin_locks_90":0},"account":{"date_opened":"2020-01-01","balance":600},"all_account_cards":[],"declines":[],"successful_last_7d":[],"successful_atm_withdrawals":[],"overdraft_fees":[]}' | python3 scripts/score_pin_lock.py
```

The example is only an interface demonstration. In a real investigation, an empty decline list is a data-quality gap, not evidence that risk is low.
