---
name: debit-card-atm-decline-investigation
description: Investigate one or more debit-card ATM declines, including shared-terminal incidents, by verifying identity and authority, retrieving linked accounts, cards, and transaction history, applying decline-code procedures, and safely handling any eligible temporary ATM-limit request. Use when a customer reports an ATM withdrawal decline or asks why several debit cards fail at an ATM.
---

# Debit-card ATM decline investigation

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

This workflow diagnoses ATM declines and may support a temporary ATM-limit increase only after every applicable prerequisite is complete. Account/card retrieval and explanation are read-only investigation; freezing, unfreezing, clearing security protections, changing limits, PIN changes, replacement orders, and transfers are banking actions.

Do not infer a decline code from the words “transaction declined.” Do not claim that an ATM, its operator, the bank, or a specific card is at fault until the required checks establish it. A configured daily limit alone is not the available amount: prior same-day withdrawals and available funds can still cause a decline.

For a parent or guardian handling a minor’s account, verify the caller’s identity and verify the recorded authority relationship (for example, the minor record’s `parent_user_id`) before disclosing account details or taking an action. If authority is absent, conflicting, or cannot be verified, do not disclose protected details or act on that account.

## Required inputs to collect

Collect or confirm:

- the caller’s full name or account email, and each affected cardholder’s name;
- standard identity verification for the caller: confirm any two of date of birth, email, phone number, and street address against the user record; then obtain the current timestamp and call `log_verification` with all required record fields;
- for another cardholder, the relationship and authority; verify the relationship in the returned customer records;
- for each attempt: card/account identification (last four digits where possible), requested cash amount, whether the cardholder personally made the attempt, the exact displayed code/message, and whether cash was dispensed;
- whether all attempts occurred at the same terminal, plus operator/location or receipt information if available;
- whether the customer recognizes recent transactions and whether the card is lost, stolen, damaged, or currently traveling.

If the customer cannot provide an exact code, proceed as a generic decline investigation. Do not require unavailable ATM operator details before investigating.

## Investigation workflow

1. **Verify identity and authority first.** Locate customer records with the appropriate user lookup. Ask for two identity fields; do not treat a name alone as verification. Get the current time and create the verification audit record after two fields match. For a minor/teen account, confirm the caller is an authorized parent or guardian through the account-holder record. If the caller is not verified, limit the response to general, non-account-specific guidance.

2. **Get all relevant accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` for each cardholder. Identify the checking account associated with each reported debit card, recording `account_id`, `account_class`, `status`, `balance`, and `date_opened`. Do not assume accounts with similar product names belong to the same person.

3. **Get cards per checking account.** Unlock and call `get_debit_cards_by_account_id_7823(account_id)` for every relevant checking account. Match the customer’s card by last four digits when available. Record the `card_id`, linked account, status, issue reason, issuance date, ATM limit and usage/count fields when returned, as well as fraud-alert, velocity-block, PIN, geographic, and transaction-restriction fields if returned.

4. **For an unknown/generic decline, apply this order independently to every affected card.**
   1. Card status: FROZEN, CLOSED, and PENDING each have a distinct resolution. Only an ACTIVE card proceeds.
   2. Linked account status: if not OPEN, state that a restriction prevents transactions. For SUSPENDED or RESTRICTED status, do not reveal the specific restriction; direct the customer to a branch or the dedicated account-services line, `1-800-RHO-ACCT`.
   3. Fraud alert: a customer-initiated alert may only be cleared after identity verification and confirmation that recent transactions are legitimate. A bank-initiated alert must not be cleared; transfer to the security team.
   4. Velocity block: explain its temporary nature. It normally expires after 30 minutes. Early clearing requires verified identity and the `velocity_clear` reason through `clear_debit_card_fraud_alert_4892`.

5. **Check whether the requested withdrawal can be authorized.** For an active card on an open account, compare the requested cash amount with `daily_atm_limit`, `daily_atm_used`, and any daily count limit/usage returned. Then retrieve transaction history with `get_bank_account_transactions_9173(account_id)` and review recent posted and pending ATM withdrawals, pending debits, and overdraft fees. Assess the available balance, not merely the posted balance. Authorization holds may not appear as posted transactions; ask the customer about recent gas, hotel, rental-car, restaurant, or other merchant holds when the balance appears sufficient.

   The packaged script can consistently calculate known remaining daily limit and flag missing decision inputs; it is an advisory aid, not authorization to take an action.

6. **Consider the common-terminal pattern carefully.** If multiple otherwise eligible cards fail at the same ATM, record the common terminal and time. A terminal-specific block is only established by Code 58 or reliable system information. For Code 58, explain that the terminal is flagged and recommend a different register/terminal or merchant; no agent-side change is available. For temporary network/issuer codes (19, 91, 92, or 96), advise the documented immediate or short delayed retry as appropriate and a different terminal/payment method. Without a code or system evidence, present the common ATM as a possibility, not a conclusion. Avoid repeated retries at the same machine when it has repeatedly declined transactions.

7. **Use code-specific handling when a code is known.**
   - **51:** review balance, pending debits, authorization holds, and ATM/POS overdraft settings. Offer funding or a smaller transaction only after checking the relevant action prerequisites.
   - **52:** confirm checking-account status; a closed linked account cannot support the card. An open account with persistent Code 52 may be a synchronization issue; advise waiting 10–15 minutes.
   - **55 or 75:** do not unlock a PIN-locked card casually. Follow the separate PIN-lock fraud-risk assessment before any unlock; a `security_hold`, suspicious pattern, or unsuccessful verification requires security escalation.
   - **57:** inspect applicable ATM/international, geographic, merchant, and teen/parental restrictions. Do not modify parental controls without guardian authorization. Do not remove gambling/adult MCC blocks by phone.
   - **61:** explain the actual configured limit, amount already used, and known remaining amount. Check possible third-party ATM limits, which cannot be overridden.
   - **62:** review geographic restrictions and recent issuance timing.
   - **65:** explain the daily count limit and reset timing; count limits are normally not increased.
   - **83:** explain that PIN verification had a technical problem rather than asserting the PIN was wrong; suggest a retry, different terminal, or waiting 10–15 minutes if persistent.
   - **41:** a lost card cannot be reactivated. Check replacement status and follow the appropriate replacement/activation process.
   - **43:** use enhanced verification. A stolen card cannot be reactivated; if the customer denies reporting it stolen, transfer to security.
   - **04, 07, 34, or 59:** do not disclose the internal code or fraud rationale. Provide the prescribed neutral branch/in-person response and escalate when pressed.

8. **Temporary ATM-limit increase (only when requested and needed).** Before calling `request_temporary_debit_card_limit_increase_8374`, verify and document all of: verified caller identity and authority; cardholder/account ownership; linked checking account is OPEN; account age is at least 60 days; no overdraft fee in the last 30 days according to transaction history; card status is ACTIVE; no earlier temporary increase in the prior 24 hours; current daily use and the requested amount; available balance; third-party terminal constraint; and the customer’s explicit confirmation of the proposed new limit and 24-hour duration. The proposed `new_limit` must be no more than 150% of the current limit. Unlock the tool, then call it with `card_id`, `limit_type: "atm"`, and the confirmed `new_limit`. A request is not a guarantee of approval. Do not propose an increase when the normal limit and known remaining limit already cover the requested cash; continue the decline diagnosis instead.

9. **Close the interaction.** Summarize verified findings for each card separately, say what is known versus unknown, provide the safe next step, and avoid exposing security-only details. If repeated declines persist after checks, collect screenshots/receipt, timestamps, workflow, device/app/browser details where relevant, and escalate with logs. Record reasons when a security alert or velocity block is cleared.

## Tool use

Specialized bank tools are discoverable. Before each first use, call `unlock_discoverable_agent_tool` with the exact tool name, then use `call_discoverable_agent_tool` with a JSON-string `arguments` object. Relevant tool names are:

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `get_bank_account_transactions_9173`
- `clear_debit_card_fraud_alert_4892`
- `request_temporary_debit_card_limit_increase_8374`

Never call a discovered action tool merely because the script reports eligibility. The executor must independently complete the documented checks, obtain customer confirmation where required, and then use normal banking tools.

For a bank-initiated fraud alert, failed/uncertain identity verification, suspected fraud, or a stolen-card denial, transfer to a human agent with `reason: "fraud_or_security_concern"` and a concise factual summary. Use `technical_system_error` when a documented persistent systems issue—not an unverified terminal theory—prevents completion.

## Script interface and validation

Run `scripts/assess_atm_declines.py` with JSON on stdin. It emits JSON only.

Input schema:

```json
{
  "cards": [
    {
      "label": "customer-selected label",
      "account_id": "string or null",
      "card_id": "string or null",
      "status": "ACTIVE|FROZEN|PENDING|CLOSED|other|null",
      "requested_amount": 0,
      "daily_atm_limit": 0,
      "daily_atm_used": 0,
      "daily_transaction_count": 0,
      "daily_transaction_limit": 0,
      "account_status": "OPEN|other|null",
      "account_age_days": 0,
      "overdraft_fee_last_30_days": true,
      "temporary_increase_last_24h": false,
      "proposed_new_limit": 0
    }
  ]
}
```

All monetary values must be non-negative numeric values. Unknown fields may be `null`; do not replace unknown values with zero. `overdraft_fee_last_30_days` and `temporary_increase_last_24h` may be `true`, `false`, or `null`. Omit `proposed_new_limit` unless the customer has actually requested and confirmed a temporary increase.

Validation: the result reports `known_remaining_atm_limit` only when both current limit and amount used are known; it labels limit coverage as `within_known_remaining`, `exceeds_known_remaining`, or `unknown`. It separately lists missing or failed prerequisites for a temporary increase and checks the 150% ceiling. Review `errors` before relying on any assessment. A result of `eligible` means only that supplied facts meet the mechanical criteria; it never substitutes for identity, authority, balance, terminal-limit, fraud, or confirmation checks.

Example runnable call:

```json
{"cards":[{"label":"primary card","account_id":"account-from-runtime","card_id":"card-from-runtime","status":"ACTIVE","requested_amount":120,"daily_atm_limit":300,"daily_atm_used":50,"account_status":"OPEN","account_age_days":90,"overdraft_fee_last_30_days":false,"temporary_increase_last_24h":false}]}
```
