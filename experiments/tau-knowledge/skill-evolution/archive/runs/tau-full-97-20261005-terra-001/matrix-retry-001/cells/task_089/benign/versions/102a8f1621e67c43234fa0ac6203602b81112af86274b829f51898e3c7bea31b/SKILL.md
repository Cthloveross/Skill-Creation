---
name: multi-card-atm-decline-investigation
description: Investigate ATM debit-card declines for a verified customer with one or more checking accounts. Use when card/account status, same-day ATM usage, published ATM limits, available balance, security controls, a temporary ATM-limit request, or a requested human escalation must be handled.
---

# Multi-card ATM decline investigation

## Scope and safety

Treat every reported card independently, but use account-level evidence where it reliably identifies the card. Do not reveal internal decline codes, fraud-alert sources, risk scores, or sensitive account/card data beyond what is needed to resolve the verified customer's request.

A withdrawal may be declined because of card status, account status, a security control, PIN lock, daily ATM availability, available balance, pending activity, or an ATM operator's independent limit. Do not promise that a bank-side change overrides a third-party ATM's own cash-dispensing limit.

Do not search broadly for a child or disclose/act on a teen card based only on a first name and an adult's assertion of parenthood. Establish the account/card relationship and the verified adult's authority from returned account/card information before discussing it.

## Required record and verification

1. Identify the customer and compare at least two supplied identity fields (date of birth, address, email, or phone) to the returned profile.
2. Obtain the current timestamp with `get_current_time` and call `log_verification` with the complete returned profile and timestamp after the comparison succeeds.
3. Unlock and retrieve:
   - `get_all_user_accounts_by_user_id_3847` for all customer accounts;
   - `get_debit_cards_by_account_id_7823` for every returned checking account; and
   - `get_bank_account_transactions_9173` for every identified checking account.
4. Retain account ID, account type/class, account status, balance, opening date, card ID/owner/status, card ATM-limit fields, security/PIN fields, and relevant posted or pending activity.
5. Obtain the attempted amount for each card, cash-dispense result, ATM message/location if known, and the current date. Use the account's applicable published product policy if a returned card record omits its ATM limit.

Only checking accounts are debit-card candidates. Never expose full card numbers.

## Determine daily ATM availability correctly

For each active reported card, determine the ordinary daily amount remaining as:

`remaining = max(0, published_or_returned_daily_ATM_limit - same_day_ATM_used)`

Use a returned card-level `daily_atm_used` first. If it is absent, sum same-day ATM-withdrawal records that explicitly identify that card. Account-level history is also reliable card usage **when the retrieved account has exactly one active card**: attribute the account's same-day ATM-withdrawal total to that sole active card. Do not reject this evidence merely because transactions omit a card ID. If there are multiple active cards and no card-specific attribution, explain only the account-level activity and obtain more information rather than assigning it to one card.

Count all relevant same-day withdrawal activity indicated by the records, including pending activity when it is already consuming daily-limit availability. Do not treat ATM fees as cash withdrawals.

Use the supplied `scripts/assess_atm_declines.py` helper after normalizing tool records. It is read-only and helps make attribution and arithmetic explicit.

```sh
python3 scripts/assess_atm_declines.py < investigation.json
```

Input is one JSON object:

```json
{
  "current_time": "2025-01-31 12:00:00 EST",
  "accounts": [{
    "account_id": "string",
    "account_type": "checking",
    "account_class": "string",
    "status": "OPEN",
    "balance": 0,
    "date_opened": "YYYY-MM-DD",
    "published_daily_atm_limit": 0
  }],
  "cards": [{
    "card_id": "string",
    "account_id": "string",
    "status": "ACTIVE",
    "daily_atm_limit": 0,
    "daily_atm_used": 0
  }],
  "attempts": [{"card_id": "string", "requested_amount": 0}],
  "transactions": [{
    "account_id": "string",
    "card_id": "optional string",
    "date": "MM/DD/YYYY or YYYY-MM-DD",
    "type": "atm_withdrawal",
    "amount": -0.0,
    "status": "posted"
  }]
}
```

It emits JSON with `cards`, `errors`, and `warnings`. Each card result reports the selected limit source, usage source, remaining limit, and a preliminary next step. Validate that there are no input `errors`; inspect warnings before relying on a result. The helper never calls a banking tool and never performs an action.

## Diagnose in required order

For each card, record evidence and resolve these checks in this order before presenting a generic limit or retry explanation:

1. **Card status**
   - `FROZEN`: ask the verified owner whether to unfreeze. With consent and an open linked account, unlock and call `unfreeze_debit_card_3893`; confirm the result.
   - `CLOSED`: explain it is no longer active and review any applicable replacement card.
   - `PENDING`: follow the issue-reason-specific activation procedure.
   - `ACTIVE`: continue.
2. **Linked checking-account status**
   - If not `OPEN`, do not disclose restriction details. Explain that an account restriction prevents transactions and direct the customer to a branch or `1-800-RHO-ACCT`.
3. **Fraud alert**
   - A bank-initiated alert must not be cleared. Transfer to security with `fraud_or_security_concern`.
   - A customer-initiated alert can be cleared only after verification and the customer confirms the relevant activity is legitimate. Unlock and call `clear_debit_card_fraud_alert_4892` with `reason: "customer_verified"`.
   - If the source is unknown, do not clear it; obtain the source or escalate for security review.
4. **Velocity block**
   - Explain that it normally lifts after 30 minutes. After verification, a reasonable explanation, and consent, unlock and call `clear_debit_card_fraud_alert_4892` with `reason: "velocity_clear"`.
5. **PIN lock**
   - If `pin_locked` is true, use `references/pin_lock_protocol.md` and complete its required risk assessment before an unlock decision.
6. **Daily limit and available funds**
   - State the published/returned daily limit, same-day withdrawal total, and exact remaining ATM amount whenever evidence is reliable. Explicitly explain when the requested amount is greater than that remaining amount.
   - Review account balance, pending debits, reported authorization holds, and overdraft settings. A no-overdraft account declines an ATM withdrawal beyond available funds.
   - If the card/account/security checks do not explain the issue, a terminal or network problem remains possible. Recommend a different ATM or a brief retry, not repeated attempts at the same machine.

## Customer-facing explanation

Give an empathetic, concrete conclusion for each authorized card. The explanation must include the actual daily ATM limit and arithmetic, not merely say that a limit may exist. For example, communicate the values determined from the record in this form:

- “Your daily ATM limit is `$LIMIT`. You have withdrawn `$USED` today, so `$REMAINING` remains.”
- “The attempted `$REQUESTED` is above the remaining `$REMAINING`, which explains the ordinary daily-limit decline.”

Also explain that an outside ATM can impose a lower independent limit. Do not use ambiguity about account-level records when the account has one retrieved active card; in that case the account's same-day withdrawal total is usable for the explanation.

## Temporary ATM-limit increase

Handle a request for a temporary ATM increase only for an authorized adult card. Before the request, establish from the record that:

- the linked checking account is `OPEN` and at least 60 days old;
- the card is `ACTIVE`; and
- the account history has no overdraft fee in the prior 30 days.

The temporary limit may be at most 150% of the current daily limit and lasts 24 hours. If a customer asks for an increase to cover a stated ATM cash need, calculate the least required new daily limit as:

`needed_new_limit = same_day_ATM_used + requested_cash_amount`

If `needed_new_limit` is at or below 150% of the current limit and all eligibility facts are satisfied, the stated request authorizes the temporary-limit request. Do not invent a requirement for separately returned card-level usage when the sole-active-card account history establishes usage. Unlock `request_temporary_debit_card_limit_increase_8374` and call it with:

```json
{"card_id":"returned card ID","limit_type":"atm","new_limit":needed_new_limit}
```

Confirm the tool result, the 24-hour duration, and that the ATM operator may still impose its own cap. If the required amount exceeds the maximum, explain the maximum and offer lawful alternatives. If available evidence shows an already granted temporary increase in the prior 24 hours, do not request another one; otherwise do not manufacture an unavailable-history prerequisite. Never remove or override a teen/minor account's safeguards.

## Transfers and escalation

An explicit customer request for a human is an instruction to transfer, not an invitation to offer transfer. Call the native `transfer_to_human_agents` tool immediately after such a request, using the highest applicable reason and a useful factual summary.

- Use `fraud_or_security_concern` for bank-initiated security issues, suspected compromise, or an ineligible high-risk PIN outcome.
- Use `technical_system_error` only when a tool/system error prevents completion.
- Use `customer_frustrated_demands_human` when general frustration is clear; otherwise use `customer_requests_human_no_specific_reason` for a plain preference for a person.

The summary should state the verified customer's issue, authorized accounts/cards checked, decline amounts, applicable daily-limit/usage findings, status/security findings, actions completed or attempted, and any unresolved need. Do not include unnecessary sensitive details. After a successful transfer call, tell the customer the handoff is underway.

## Closeout

Document the time, ATM/location if known, attempted amounts, same-day withdrawals, status/security findings, published limits and calculations, pending-activity review, tool actions/results, and advice. A transfer between accounts is separate from resolving an ATM-limit/security issue; execute it only after the customer supplies a distinct source, destination, positive amount, and authorization and all transfer preconditions are met.
