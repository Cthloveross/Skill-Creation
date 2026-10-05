---
name: multi-card-atm-decline-investigation
description: Investigate ATM debit-card declines for a verified customer across checking accounts, calculate policy-backed remaining daily ATM availability from transaction history, process eligible temporary ATM-limit increases, and complete requested human handoffs.
---

# Multi-card ATM decline investigation

## Scope, privacy, and safety

Investigate every reported card independently. Do not disclose information about, search for, or change a card merely because the verified adult names a relative. Establish the particular account/card, the cardholder relationship, and the verified customer's authority from returned records first. A first name and an assertion of guardianship are not sufficient evidence for a teen account.

Do not expose full card numbers, internal decline codes, fraud-alert sources, or PIN-risk scoring. A Rho-Bank daily limit is separate from, and cannot override, a third-party ATM's own dispensing limit.

## Required evidence and ordering

Do not stop at card status if transaction history and an applicable product policy support a limit calculation.

1. **Verify the adult customer.** Match at least two supplied identity fields among date of birth, address, email, and phone against a returned profile. Obtain the current timestamp and call `log_verification` with the complete returned profile and timestamp.
2. **Retrieve checking-account evidence.** Unlock and use `get_all_user_accounts_by_user_id_3847`. For every returned checking account, unlock and use `get_debit_cards_by_account_id_7823` and `get_bank_account_transactions_9173`.
3. **Retain required facts.** For every authorized reported card retain the account ID/type/class/status/balance/opening date; card ID/owner/status/issue date; security and PIN fields; attempted withdrawal; and posted or pending transaction activity.
4. **Obtain applicable policy facts.** Read the supplied product-policy material for each identified account product. Extract the published daily ATM withdrawal limit when the card record does not return `daily_atm_limit`. A product policy is valid limit evidence; never describe the limit as unavailable solely because the debit-card result omitted that field.
5. **Calculate and communicate daily ATM availability immediately.** Once card lists, histories, and policy facts are available, run the packaged assessor and give the customer the concrete result for every supported authorized adult card **before** offering a temporary increase, troubleshooting, or a handoff.
6. **Diagnose remaining controls in order.** Check card status, linked account status, fraud alert, velocity block, PIN lock, daily ATM availability, then available funds/pending activity and terminal conditions.
7. **Complete requested actions.** Submit an eligible temporary increase when requested. An explicit human-transfer request requires a transfer action, not an offer.

Only checking accounts are debit-card candidates. Do not substitute credit-card retrieval for checking-account and debit-card retrieval.

## Daily ATM availability calculation

For each card:

`remaining = max(0, daily_atm_limit - same_day_atm_withdrawals)`

Use evidence in this precedence order:

1. returned card `daily_atm_used`;
2. same-day ATM-withdrawal records explicitly tagged with that card; or
3. same-day account ATM-withdrawal records when that account has exactly one retrieved `ACTIVE` card.

The third case is reliable attribution. Do not call account history ambiguous merely because it lacks a card ID if exactly one active card was returned for that account. If multiple active cards exist and the history cannot identify the card, state only the account-level activity and obtain card-specific evidence before attributing use.

Use returned `daily_atm_limit` if present; otherwise provide the applicable published product limit as `published_daily_atm_limit`. Count same-day posted withdrawals and pending ATM withdrawals that consume availability; do not count ATM fees as cash withdrawals.

Normalize the retrieved facts and run:

```sh
python3 scripts/assess_atm_declines.py < investigation.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. It makes no banking calls. Its input schema is:

```json
{
  "current_time": "YYYY-MM-DD HH:MM:SS TZ",
  "accounts": [{"account_id":"string","account_type":"checking","status":"OPEN","balance":0,"date_opened":"YYYY-MM-DD","published_daily_atm_limit":0}],
  "cards": [{"card_id":"string","account_id":"string","status":"ACTIVE","daily_atm_limit":0,"daily_atm_used":0}],
  "attempts": [{"card_id":"string","requested_amount":0}],
  "transactions": [{"account_id":"string","card_id":"optional string","date":"MM/DD/YYYY or YYYY-MM-DD","type":"atm_withdrawal","amount":-0.0,"status":"posted"}]
}
```

Inspect top-level `errors` and per-card `warnings`. For each usable assessment, use its `customer_limit_explanation` and `customer_attempt_explanation` as the required customer-facing calculation. Preserve the actual values and do not omit a supported card's result. The script's output includes sources so that the agent can explain whether the amount came from returned card data, account history, or a supplied policy.

### Mandatory customer explanation checkpoint

Before any generic troubleshooting, temporary-limit offer/request, or transfer, say the equivalent of both of these for **each** authorized active card with a usable assessment:

- “Your daily ATM limit is `$LIMIT`. You have withdrawn `$USED` today, leaving `$REMAINING`.”
- “Your attempted withdrawal of `$REQUESTED` is above the `$REMAINING` remaining, so it exceeds the ordinary daily ATM availability.”

This checkpoint is mandatory even if the customer is stranded, a requested amount is plainly too high, or the conversation may subsequently be transferred. Also say that a third-party ATM can impose a lower separate cap. A positive posted balance does not prove the full cash request is available.

## Diagnostic sequence

For each authorized card, perform and document these checks in order.

1. **Card status**
   - `FROZEN`: ask the verified owner whether to unfreeze; with consent and an open account, unlock and call `unfreeze_debit_card_3893`.
   - `CLOSED`: state that it is no longer active and review replacement options where appropriate.
   - `PENDING`: follow the issue-reason-specific activation procedure.
   - `ACTIVE`: continue.
2. **Linked account status:** if not `OPEN`, do not disclose the restriction detail. State that an account restriction prevents transactions and direct the customer to a branch or `1-800-RHO-ACCT`.
3. **Fraud alert:** never clear a bank-initiated alert; transfer to security. Clear a customer-initiated alert only after verification and confirmation that relevant activity is legitimate, using `clear_debit_card_fraud_alert_4892` with `customer_verified`. Unknown source requires more evidence or security escalation.
4. **Velocity block:** explain that it normally expires after 30 minutes. After verification, a reasonable explanation, and consent, clear it using `clear_debit_card_fraud_alert_4892` with `velocity_clear`.
5. **PIN lock:** if `pin_locked` is true, follow `references/pin_lock_protocol.md` completely before any unlock decision.
6. **Limit and funds:** complete the required daily-limit explanation. Review current balance, pending debits, authorization holds reported by the customer, and overdraft settings. Do not infer available funds from a posted balance alone.
7. **Terminal/network:** if prior checks do not explain the decline, recommend a different ATM or a brief retry, rather than repeated attempts at the same terminal.

## Temporary ATM-limit increase

Handle this only for an authorized adult card. A clear question or request for a temporary increase for the stated cash need authorizes a submission when all policy conditions are supported; do not invent a requirement for separately returned card-usage data when sole-active-card account history reliably establishes usage.

Before calling the increase tool, establish from returned records that:

- the linked checking account is `OPEN` and at least 60 days old;
- the card is `ACTIVE`; and
- the transaction history contains no overdraft fee in the prior 30 days.

Calculate:

`needed_new_limit = same_day_atm_withdrawals + requested_cash_amount`

The maximum is:

`maximum_new_limit = current_daily_limit * 1.5`

If the needed limit is at or below the maximum and there is no evidence that the card already received a temporary increase within 24 hours, unlock `request_temporary_debit_card_limit_increase_8374` and call it with:

```json
{"card_id":"returned card ID","limit_type":"atm","new_limit":needed_new_limit}
```

Confirm only the actual tool result. Explain that the temporary limit lasts 24 hours, automatically reverts, and cannot override an ATM operator's own cap. If the needed limit exceeds the maximum or any condition fails, explain the supported limiting condition and alternatives. Never remove or override minor-account safeguards.

## Human escalation is an action

For an explicit request such as “transfer,” “human,” “representative,” or a marked transfer request, call native `transfer_to_human_agents` in the next tool-action turn. Do not merely offer escalation or ask for additional information.

Choose the highest applicable reason:

- `fraud_or_security_concern` for bank-initiated security issues, suspected compromise, or an ineligible PIN-risk outcome;
- `technical_system_error` only for an actual system/tool error that prevented the request;
- `customer_frustrated_demands_human` for clear general frustration;
- `customer_requests_human_no_specific_reason` for a plain request or preference.

Include a concise factual `summary`: verification state; authorized accounts/cards checked; attempted amounts; status/security findings; daily-limit/used/remaining calculations; actions completed or attempted; and unresolved need. Avoid unnecessary personal or card data. After a successful result, tell the customer that the handoff is underway.

## Closeout

Record the timestamp, ATM/location if known, requested amounts, cash-dispense result, same-day withdrawals, status/security findings, policy/limit calculations, pending-activity review, tool calls/results, and customer advice. Do not initiate an inter-account transfer unless the customer separately identifies source and destination accounts, a positive amount, and authorization, and both accounts meet transfer preconditions.
