---
name: multi-card-atm-decline-investigation
description: Diagnose ATM debit-card declines for a verified customer across multiple checking accounts, calculate remaining daily ATM availability from card/account records and product policies, request eligible temporary ATM-limit increases, and complete requested human transfers.
---

# Multi-card ATM decline investigation

## Scope and privacy

Investigate each reported card independently. Do not disclose or take action on a card until its account, cardholder relationship, and the verified customer's authority are established by returned records. In particular, do not search for or discuss a teen card based only on a child's first name and an adult's assertion of parenthood.

Do not expose full card numbers, internal decline codes, fraud-alert sources, or PIN-risk scoring. A bank-side ATM limit does not override an ATM operator's separate dispensing cap.

## Required workflow

Perform these steps in order; do not stop after a status check when a limit calculation or requested action is supported by the records.

1. **Verify and log the adult customer.** Match at least two customer-supplied fields among date of birth, address, email, and phone against a returned profile. Obtain `get_current_time`, then call `log_verification` with the complete returned profile and timestamp.
2. **Retrieve all relevant evidence.** Unlock and call:
   - `get_all_user_accounts_by_user_id_3847`;
   - `get_debit_cards_by_account_id_7823` for every returned checking account; and
   - `get_bank_account_transactions_9173` for every identified checking account.
3. **Obtain/retain facts.** For each authorized reported card, retain account ID, type/class, status, balance, opening date, card ID, owner, status, issue date, ATM-limit and security/PIN fields, attempted withdrawal amount, and relevant posted/pending transaction activity.
4. **Calculate ordinary ATM availability.** Use the procedure below, including the product policy when a card record has no ATM-limit field.
5. **Diagnose controls in the mandated sequence.** Check card status, account status, fraud alert, velocity block, PIN lock, daily ATM availability, and available funds/pending activity.
6. **State the concrete result before offering generic troubleshooting.** For every authorized active card with reliable evidence, tell the customer the actual limit, same-day amount used, exact amount remaining, and whether the attempted amount exceeds that remainder.
7. **Perform supported actions.** When an eligible temporary-increase request is made, submit it. When the customer explicitly asks for a human, immediately call `transfer_to_human_agents`; an offer to transfer is not completion.

Only checking accounts are debit-card candidates. Never substitute a credit-card search for checking-account/card retrieval.

## Determine daily ATM availability

For each card, calculate:

`remaining = max(0, daily_atm_limit - same_day_atm_withdrawals)`

Use evidence in this precedence order:

1. returned card `daily_atm_used`;
2. same-day ATM-withdrawal transactions explicitly tagged with that card; or
3. same-day account ATM-withdrawal transactions if that account has **exactly one retrieved ACTIVE card**.

The third case is reliable attribution. Do not call account history ambiguous merely because its records omit a card ID when exactly one active card was retrieved for that account. If multiple active cards exist and records do not identify the card, explain only the account-level activity and obtain card-specific evidence before attributing usage.

Use a returned card `daily_atm_limit` when present. If omitted, apply the published policy for that identified account class/product. Product-policy limits remain usable evidence even if the debit-card lookup omits limit fields. Count same-day posted withdrawals and pending ATM withdrawals that are already consuming availability; do not count ATM fees as cash withdrawals.

Use `scripts/assess_atm_declines.py` after normalizing the tool records. The helper is read-only and must not replace review of its warnings.

```sh
python3 scripts/assess_atm_declines.py < investigation.json
```

The script accepts one JSON object on stdin and writes one JSON object on stdout:

```json
{
  "current_time": "YYYY-MM-DD HH:MM:SS TZ",
  "accounts": [{"account_id":"string","account_type":"checking","status":"OPEN","balance":0,"date_opened":"YYYY-MM-DD","published_daily_atm_limit":0}],
  "cards": [{"card_id":"string","account_id":"string","status":"ACTIVE","daily_atm_limit":0,"daily_atm_used":0}],
  "attempts": [{"card_id":"string","requested_amount":0}],
  "transactions": [{"account_id":"string","card_id":"optional string","date":"MM/DD/YYYY or YYYY-MM-DD","type":"atm_withdrawal","amount":-0.0,"status":"posted"}]
}
```

Inspect `errors` and per-card `warnings`. A usable result identifies the limit and usage sources, `remaining_atm_limit`, and a preliminary next step. The script makes no banking calls and cannot perform an action.

## Required diagnostic order

For each authorized card, evaluate and document the following in order.

1. **Card status**
   - `FROZEN`: ask the verified owner whether to unfreeze; with consent and an open account, unlock and call `unfreeze_debit_card_3893`.
   - `CLOSED`: say it is no longer active and review replacement options where appropriate.
   - `PENDING`: follow the issue-reason-specific activation procedure.
   - `ACTIVE`: continue.
2. **Linked account status**: if not `OPEN`, do not disclose the restriction; say a restriction prevents transactions and direct the customer to a branch or `1-800-RHO-ACCT`.
3. **Fraud alert**: never clear a bank-initiated alert; transfer to security. Clear a customer-initiated alert only after verification and customer confirmation that relevant activity is legitimate, using `clear_debit_card_fraud_alert_4892` with `customer_verified`. Unknown source requires further evidence or security escalation.
4. **Velocity block**: explain it normally expires after 30 minutes. After verification, a reasonable explanation, and consent, clear it with `clear_debit_card_fraud_alert_4892` and `velocity_clear`.
5. **PIN lock**: if `pin_locked` is true, follow `references/pin_lock_protocol.md` completely before any unlock decision.
6. **ATM limit and funds**: calculate and explain the daily limit/used/remaining amount. Also review current balance, pending debits, authorization holds reported by the customer, and overdraft settings. Do not represent a positive posted balance as proof that the full requested withdrawal is available.
7. **Terminal/network condition**: if no prior condition explains the decline, recommend a different ATM or a brief retry rather than repeated attempts at the same terminal.

## Customer-facing explanation checkpoint

Before concluding an investigation, provide an explicit calculation for each supported adult card, using customer-friendly currency formatting:

- “Your daily ATM limit is `$LIMIT`. You have withdrawn `$USED` today, leaving `$REMAINING`.”
- “Your attempted withdrawal of `$REQUESTED` is above the `$REMAINING` remaining, so it exceeds the ordinary daily ATM availability.”

Give this explanation whenever one-active-card account history supports the calculation. Do not say that a published limit is unavailable if the applicable product policy supplies it. Explain separately that a third-party ATM may have its own lower per-transaction or dispensing limit.

## Temporary ATM-limit increase

Handle this only for an authorized adult card. A request or clear question seeking a temporary increase for the stated cash need authorizes submission once all policy conditions are evidenced; do not add an unsupported requirement for separately returned card-usage data.

Before calling the increase tool, confirm from returned records that:

- the linked checking account is `OPEN` and has been open at least 60 days;
- the card is `ACTIVE`; and
- account history shows no overdraft fee in the preceding 30 days.

Calculate the least new daily limit that supports the stated request:

`needed_new_limit = same_day_atm_withdrawals + requested_cash_amount`

The maximum is `current_daily_limit * 1.5`. If `needed_new_limit` is at or below that maximum, and there is no evidence of an increase already granted for the card in the prior 24 hours, unlock `request_temporary_debit_card_limit_increase_8374` and call it:

```json
{"card_id":"returned card ID","limit_type":"atm","new_limit":needed_new_limit}
```

Confirm the actual tool result, that the increase lasts 24 hours and automatically reverts, and that another ATM's cap may still prevent the requested cash dispense. If the need is above the maximum or a policy condition fails, explain the limiting condition and available alternatives. Never remove or override minor-account safeguards.

## Human escalation is an action

On an explicit request such as “transfer,” “human,” “representative,” or a marked transfer request, call the native `transfer_to_human_agents` tool in the next tool-action turn. Do not merely ask whether the customer wants a transfer and do not wait for additional information.

Select the highest applicable reason:

- `fraud_or_security_concern` for bank-initiated security issues, suspected compromise, or an ineligible PIN-risk result;
- `technical_system_error` only when an actual system/tool error prevented the requested action;
- `customer_frustrated_demands_human` where general frustration is clear;
- `customer_requests_human_no_specific_reason` for a plain request or preference for a human.

Include a concise factual `summary`: verification state, authorized accounts/cards checked, attempted amounts, card/account/security findings, daily-limit calculations, actions completed/attempted, and unresolved need. Avoid unnecessary personal/card data. After a successful tool result, tell the customer the handoff is underway.

## Closeout

Record the timestamp, ATM/location if known, requested amounts, cash-dispense result, same-day withdrawals, status/security findings, limit calculations, pending-activity review, tool calls/results, and customer advice. Do not initiate an inter-account transfer unless the customer separately identifies source and destination accounts, a positive amount, and authorization, and both accounts satisfy transfer preconditions.
