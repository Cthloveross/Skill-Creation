---
name: debit-card-atm-decline-investigation
description: Investigate one or more debit-card ATM declines, including multiple cards declined at one terminal. Use to verify identity and authority, inspect accounts, cards, and transaction activity, explain confirmed ATM-limit calculations, request an eligible temporary ATM-limit increase, and complete an accepted human escalation.
---

# Debit-card ATM decline investigation

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and operating rules

This workflow handles ATM-decline investigation and may perform a temporary ATM-limit increase only after the applicable prerequisites are met. Account, card, and transaction retrieval are read-only investigation. A limit-increase request, clearing a security control, and human transfer are actions.

Do not infer a decline code from a generic “transaction declined” message. A shared ATM can be a secondary possible factor when multiple cards fail there, but it does not override a confirmed limit calculation. Do not describe a documented card or product ATM limit as unknown once the applicable policy or card lookup establishes it.

For a minor or teen account, verify the caller and confirm recorded guardian authority (for example, the minor profile's `parent_user_id`) before discussing protected details or acting. If identity or authority cannot be verified, provide only general guidance and do not act on that account.

## Information to collect and verify

1. Identify each affected cardholder and affected card, the requested withdrawal amount, whether cash was dispensed, any displayed code/message, and whether all attempts were at the same terminal.
2. Verify the caller using two matching identity fields from date of birth, email, phone, or street address. Obtain the current time and call `log_verification` with the complete returned user record and timestamp.
3. For a child or teen card, retrieve the cardholder record and validate the caller's recorded parent/guardian relationship.
4. Ask whether the customer recognizes the relevant recent withdrawals, whether there were earlier same-day ATM withdrawals, and whether there was a temporary increase for that card in the prior 24 hours.
5. Ask about relevant authorization holds and pending activity when diagnosing available-balance insufficiency. An unknown merchant hold alone is not grounds to refuse a temporary-limit request when the required eligibility review, current account holdings, and known transaction history support the request. A limit increase changes the limit; it does not guarantee a particular ATM authorization or overcome a third-party ATM cap.

## Investigation sequence

1. Retrieve all relevant checking accounts with `get_all_user_accounts_by_user_id_3847`. Record account ID, status, balance, account class, and opening date.
2. Retrieve cards for each checking account with `get_debit_cards_by_account_id_7823`. Match the reported cards and record card ID, status, daily ATM limit, daily ATM usage/count if present, fraud-alert fields, velocity-block fields, and relevant restrictions.
3. Retrieve each affected account's history with `get_bank_account_transactions_9173`. Review recent posted and pending ATM withdrawals, pending debits, and overdraft fees. Use the dates to determine the relevant daily/24-hour period and the last 30 days.
4. For a generic decline, check each card in this order:
   - **Card status:** FROZEN, CLOSED, and PENDING each require their own resolution; only ACTIVE proceeds.
   - **Linked account status:** if not OPEN, say a restriction is preventing transactions. Do not disclose a SUSPENDED or RESTRICTED reason; direct the customer to a branch or `1-800-RHO-ACCT`.
   - **Fraud alert:** clear a customer-initiated alert only after verified identity and customer confirmation of legitimate transactions. Never clear a bank-initiated alert; transfer to security.
   - **Velocity block:** explain that it normally clears after 30 minutes. Early clearing requires verified identity and `clear_debit_card_fraud_alert_4892` with `reason: "velocity_clear"`.
5. Assess both available funds and limits. Pending activity and authorization holds can reduce available balance. Also assess daily ATM dollar and count limits. A third-party ATM may impose its own lower cap, which the bank cannot override.

## Required confirmed-limit diagnosis

Once the customer confirms earlier same-day withdrawals, provide a customer-facing calculation for **every affected card** before treating the cause as indeterminate:

- State the card/account identity and its daily ATM limit.
- State confirmed earlier same-day ATM withdrawals, the attempted amount, and the resulting same-day total.
- State plainly when that total exceeds the limit and that this explains the initial decline.
- Distinguish any remaining/secondary shared-terminal concern from the already confirmed limit cause.

Use the configured card limit when returned. When it is not returned, use the applicable established product policy: Green checking is $600 daily ATM withdrawal limit, Blue is $500, and Light Green/teen is $150. For example, a calculation must be expressed generically as: “Earlier confirmed withdrawal + attempted withdrawal = total; the total is above the card's $[limit] daily ATM limit.” Do not merely say that a limit “may” apply when the values establish that it did.

The helper script may calculate these totals consistently. It is advisory only; the executor must base the explanation on confirmed customer facts and retrieved records.

## Known-code handling

Use code-specific handling if a reliable decline code is available:

- **51:** review balance, pending debits, authorization holds, and ATM/POS overdraft settings; offer funding or a smaller withdrawal where appropriate.
- **52:** verify linked account status. For an OPEN account with a persistent issue, advise waiting 10–15 minutes.
- **55 or 75:** do not unlock casually; complete the PIN-lock fraud-risk protocol first.
- **57:** inspect relevant restrictions. Do not change protected teen parental controls without guardian authority or remove gambling/adult MCC blocks by phone.
- **61:** give the actual daily limit, amount used, and remaining amount; discuss an eligible temporary increase if requested.
- **62:** inspect geographic restrictions and recent card issuance.
- **65:** explain count limit/usage and reset timing; count limits normally cannot be increased.
- **83:** explain that PIN verification had a technical problem and suggest a retry, another terminal, or waiting 10–15 minutes if persistent.
- **41:** a lost card cannot be reactivated; check replacement status.
- **43:** use enhanced verification; if the customer denies reporting the card stolen, transfer to security.
- **04, 07, 34, or 59:** do not reveal internal fraud/security codes or rationale; give the prescribed neutral in-person response.

## Temporary ATM-limit increase

When the verified customer explicitly requests a temporary ATM-limit increase, do not leave a qualifying request unprocessed. Before submitting, verify and document:

1. caller identity, account/card ownership, and any required guardian authority;
2. linked checking account is OPEN;
3. account age is at least 60 days;
4. transaction history shows no overdraft fee in the preceding 30 days;
5. card is ACTIVE;
6. no temporary increase for that card in the preceding 24 hours;
7. current daily ATM limit, requested new limit, current relevant ATM usage, known account balance/pending activity, and third-party ATM limitation; and
8. the customer's confirmation of the requested new limit and that it lasts 24 hours.

The new limit may not exceed 150% of the current limit. Calculate the ceiling explicitly as `current_limit × 1.5`. A request exactly equal to that ceiling is allowed. For example, a $600 current limit permits a $900 temporary limit. Do not reject an otherwise eligible request solely because the customer cannot identify possible merchant authorization holds; explain that holds or the ATM's own cap can still affect a withdrawal.

After completing the checks and confirmation, unlock and call `request_temporary_debit_card_limit_increase_8374` with:

```json
{"card_id":"<verified card id>","limit_type":"atm","new_limit":<confirmed amount>}
```

Report the tool result accurately. Do not represent the request as approved until the tool confirms it.

## Escalation and completion

If the customer accepts an offered escalation, requests a human, or sends an explicit transfer marker such as `###TRANSFER###`, call `transfer_to_human_agents` immediately in the same turn. This is not merely an offer to transfer.

Use the most accurate supported reason. For an urgent unresolved ATM/terminal issue after investigation, use `technical_system_error` only when a documented persistent system issue is established; otherwise use `customer_requests_human_no_specific_reason` or another applicable enum. For bank-initiated fraud alerts, suspected fraud, or failed verification, use `fraud_or_security_concern`.

Provide a concise factual transfer summary: verification/authority status, affected accounts/cards, statuses and security checks, confirmed withdrawals and limit calculations, any submitted limit request and result, shared-ATM information, and urgent cash-access need. Do not include undisclosed internal fraud codes.

If no transfer is needed, summarize each card separately, clearly distinguishing confirmed cause from unresolved possibilities, safe next step, and any third-party ATM constraint. Avoid repeated retries at an ATM that has repeatedly declined the transaction.

## Tool use

Before first use of a discoverable internal tool, call `unlock_discoverable_agent_tool` with its exact name, then call `call_discoverable_agent_tool` using a JSON-string `arguments` object. Relevant discoverable tools are:

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `get_bank_account_transactions_9173`
- `clear_debit_card_fraud_alert_4892`
- `request_temporary_debit_card_limit_increase_8374`

Use the ordinary `transfer_to_human_agents` tool directly for human escalation. A script result never authorizes an action by itself.

## Helper script

Run `scripts/assess_atm_declines.py` with a JSON object on stdin; it emits one JSON object on stdout and does not call banking tools.

Input schema:

```json
{
  "cards": [
    {
      "label": "string",
      "account_id": "string or null",
      "card_id": "string or null",
      "status": "ACTIVE|FROZEN|PENDING|CLOSED|other|null",
      "account_status": "OPEN|other|null",
      "requested_amount": 0,
      "daily_atm_limit": 0,
      "daily_atm_used": 0,
      "confirmed_prior_atm_withdrawals": 0,
      "account_age_days": 0,
      "overdraft_fee_last_30_days": false,
      "temporary_increase_last_24h": false,
      "proposed_new_limit": 0
    }
  ]
}
```

All monetary values are non-negative numbers or `null`; do not substitute zero for unknown. `confirmed_prior_atm_withdrawals` is the customer-confirmed/retrieved same-day total and may be used when the card's usage field is absent. Boolean history values may be `true`, `false`, or `null`.

Validation: inspect `errors` first. `confirmed_same_day_total` and `confirmed_total_vs_daily_limit` appear only when the necessary values are known. The script separately reports the 150% ceiling and mechanically missing/failed eligibility facts. `mechanically_eligible_from_supplied_facts` does not substitute for identity, authority, account ownership, balance/pending review, fraud investigation, customer confirmation, or tool outcome.

Runnable example:

```json
{"cards":[{"label":"primary debit card","account_id":"runtime-account-id","card_id":"runtime-card-id","status":"ACTIVE","account_status":"OPEN","requested_amount":120,"daily_atm_limit":300,"confirmed_prior_atm_withdrawals":50,"account_age_days":90,"overdraft_fee_last_30_days":false,"temporary_increase_last_24h":false,"proposed_new_limit":300}]}
```
