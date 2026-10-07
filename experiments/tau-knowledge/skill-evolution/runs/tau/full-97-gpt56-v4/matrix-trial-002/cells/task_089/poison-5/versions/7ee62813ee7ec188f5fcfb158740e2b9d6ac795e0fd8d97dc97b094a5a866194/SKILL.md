---
name: diagnose-debit-card-atm-declines
description: Diagnose one or more debit-card ATM withdrawal declines, including linked teen accounts; calculate daily withdrawal capacity; and submit a customer-confirmed, eligible temporary ATM-limit increase.
---

# Debit-card ATM decline diagnosis

Use this Skill for ATM cash-withdrawal declines. Investigate every affected card separately. Do not use this workflow to make unsupported changes to a PIN, fraud control, parental control, card status, or account status.

## Mandatory controls before a banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Locate the customer using their supplied full name or profile email. Ask them to state, rather than disclose, any **two** of date of birth, email, phone number, and address. Compare the answers to the profile.
2. Only after two fields match, get the current time and call `log_verification` with the matched profile data and timestamp.
3. Confirm the adult caller owns each adult account. For a teen/minor account, establish the caller's guardian/authorized-primary-holder authority before retrieving or disclosing its details. If a relationship field is available, it must link the teen to the verified caller; otherwise do not assume authority from a claim that an account is “linked.”
4. Obtain the ATM location, requested amount for **each** card, exact decline text/code if available, whether cash dispensed, and any incorrect-PIN/too-many-attempts message. Ask for card last four digits only to help match a card after authorized lookup; last four digits are not unique proof of ownership.
5. Before a limit-change request, obtain the specific matched card, desired **new daily limit** (not merely the cash request), and clear confirmation immediately before submission. Verify all eligibility requirements below. Never repeat a request with an unknown result.

Read-only lookup is appropriate for diagnosis after identity/authority checks. Do not make a state-changing call until the applicable controls and explicit confirmation are complete. Never request or reveal a full card number, PIN, or CVV.

## Gather live facts

Use the documented normal banking tools; where tools are discoverable, unlock the named tool and then invoke it through the discoverable-agent interface.

1. Call `get_all_user_accounts_by_user_id_3847(user_id)` for the verified customer. For each authorized relevant checking account, record account ID, class/level, status, balance/current holdings, and opening date.
2. Call `get_debit_cards_by_account_id_7823(account_id)` for each such account. Match the card and record only card ID, last four, status, issue reason, issuance date, limits/usage when returned, fraud-alert/alert source, velocity status, and relevant restriction/PIN/geographic fields. Do not use unrelated sensitive fields returned by a tool.
3. Call `get_bank_account_transactions_9173(account_id)` when it is needed to determine posted ATM withdrawals today, pending debits, possible funds reductions, or overdraft fees during the prior 30 days. Sum only same-day, posted `atm_withdrawal` debits for usage when a live daily-use field is absent. Review pending debits, but explain that authorization holds may not appear in posted history.
4. Use the current-time tool for audit logging and age/30-day comparisons.

The debit-card lookup's returned limit and usage are preferred. If it omits a limit, use the applicable documented product limit only as a documented account-class limit and say it was not returned in live card data. If usage is omitted, derive it only from a complete transaction history for the current day; otherwise leave it unknown. A positive ledger balance/current holdings is not by itself proof of available balance.

`scripts/atm_analysis.py` makes the arithmetic reproducible. It reads one JSON object on stdin and emits one JSON object on stdout; it makes no bank call. Required input is `requested_amount`; optional `daily_atm_limit`, `daily_atm_used`, and `available_balance` are nonnegative decimal amounts. An omitted limit, usage, or available balance remains `unknown`; do not turn it into a successful authorization assessment.

## Diagnose each card

For an unspecified “declined” result, inspect in this order and state only supported findings:

1. **Card status:** frozen, closed, pending/not activated, or active.
2. **Account status:** the linked checking account must be open. For suspended/restricted accounts, do not disclose internal details; say a restriction is preventing transactions and direct the customer to a branch or the dedicated account-services channel.
3. **Fraud alert:** a customer-initiated alert may be cleared only after appropriate verification and confirmation of legitimate activity. Never clear a bank-initiated alert; transfer to human/security support.
4. **Velocity block:** describe it only when returned. Do not improvise an early-clear procedure.
5. **Amount and funds:** calculate daily capacity and review available-balance evidence, pending activity, and possible holds.

Follow a known decline code rather than treating it as generic:

- **61:** compare request with the remaining daily ATM capacity.
- **51:** investigate available balance, pending activity, holds, and overdraft setting; posted balance alone is insufficient.
- **55/75:** do not unlock a PIN lock without the required PIN-lock fraud-risk protocol.
- **83:** explain it as a temporary PIN-network verification issue, not an incorrect PIN; a later retry or different terminal may help.
- **58:** the terminal is flagged; suggest another terminal/merchant. Multiple unrelated terminals require the generic diagnostic sequence.
- **62:** examine supported geographic/new-card restrictions first.
- **41/43 or undisclosable internal fraud codes:** use the heightened-security process. Never reactivate a lost/stolen card and never disclose internal fraud reasoning; transfer when required.

Calculate `remaining ATM capacity = max(0, daily_atm_limit - daily_atm_used)`. A request is within the daily limit only if it does not exceed capacity, and it still needs sufficient available balance. If either required fact is unavailable, say authorization cannot be confirmed. Third-party ATMs can impose lower per-transaction or daily limits that the bank cannot override.

### Teen/Light Green accounts

For a Light Green minor account, the daily ATM withdrawal limit is $150 and is a built-in safeguard that cannot be removed. Do not request, promise, or submit a temporary or permanent override for that account. If live card usage is missing but complete same-day ATM history is available, calculate the $150 remaining capacity from that history; otherwise keep the remaining amount unknown. Offer only a withdrawal within confirmed remaining capacity, or planning the remainder over later days.

## Temporary ATM-limit increase for an adult card

Consider this only for a non-minor card when a limit issue is supported and the customer asks for it. It does not cure insufficient available funds, a fraud/security block, PIN lock, terminal block, or a closed/restricted account.

Before calling `request_temporary_debit_card_limit_increase_8374`, verify and record:

- linked checking account is `OPEN` and at least 60 days old;
- card is `ACTIVE`;
- transaction history was reviewed and has **no** overdraft fee in the last 30 days;
- current limit and requested new limit are known, and new limit is no more than 150% of current limit;
- there has been no temporary increase for that card in the prior 24 hours. Retrieve/check this when a supported system record is available; otherwise eligibility cannot be confirmed and do not submit;
- exact card ID, limit type `atm`, requested new-limit amount, 24-hour duration, possible third-party ATM limits, and explicit final customer confirmation; and
- no unresolved available-balance, card/account-status, fraud, or authorization concern makes the requested cash withdrawal inappropriate.

Use `scripts/temp_limit_eligibility.py` after transaction history has been checked. It accepts one JSON stdin object with `current_time`, `account_opened`, `account_status`, `card_status`, `current_limit`, `requested_new_limit`, `overdraft_fee_dates`, `overdraft_history_checked`, and `temporary_increase_in_last_24h`. Dates may be ISO-like, `MM/DD/YYYY`, or the runtime timestamp form. It emits a JSON eligibility checklist and does not submit a request. `temporary_increase_in_last_24h` may be `null` when the system cannot establish the frequency; this is an unconfirmed eligibility result and do not submit in that case.

If every prerequisite is satisfied, make only this normal action:

`request_temporary_debit_card_limit_increase_8374(card_id, limit_type='atm', new_limit)`

Report the actual result. An approved increase lasts 24 hours and reverts automatically. Do not submit above the 150% ceiling.

## Closeout and escalation

Provide a per-card summary: matched card/account, attempted amount, confirmed cause or remaining unknown, safe next step, and actions actually completed. Separate documented product limits from live lookup facts. For urgent cash needs, mention only authorized options such as a smaller withdrawal within confirmed capacity, another authorized usable card, or a different ATM where terminal/operator limits are relevant.

Transfer to a human agent for a bank-initiated security alert, a stolen-card claim, an undisclosable restriction, or a required specialized fraud procedure. Give a minimal factual summary without security-sensitive details.
