---
name: investigate-atm-debit-card-limits
description: Diagnose ATM cash-withdrawal declines and, only with authorization and satisfied eligibility, request a temporary ATM limit increase for an identified debit card. Use for one or more cards that declined at an ATM, including a request to check remaining ATM limit or raise it temporarily.
---

# Investigate ATM Debit-Card Limits

Use this Skill to distinguish an ATM-limit issue from card, account, balance, security, or ATM-terminal problems. Do not assume a generic ATM decline is an exceeds-limit decline, and do not infer an effective limit from an account product description when the debit-card lookup provides the card's actual current limit.

## Required runtime inputs

Collect or retrieve, at runtime:

- The requesting customer's identity and authority for each card being discussed.
- The affected card(s), linked checking account(s), attempted withdrawal amount(s), and, if known, the ATM/operator and attempt time.
- Current time, for account-age and 30-day overdraft checks.
- Account data: `account_id`, `account_type`, `status`, `balance`, and `date_opened`.
- Debit-card data: `card_id`, `account_id`, `user_id`, `status`, `daily_atm_limit`, and, when returned, `daily_atm_used`, fraud-alert, velocity-block, and PIN-lock fields.
- Transaction history for each linked account, including transaction date, type, amount, and pending/posted status.

Names, an account relationship, or knowing a card type are not identity verification. Before disclosing account-specific balances, usage, limits, card status, or taking card action, verify the relevant authorized person using two of the four recorded identity fields (date of birth, email, phone number, address). Retrieve the current timestamp and create `log_verification` only after the two fields match. Do not ask the customer to provide a PIN.

For a teen card, do not alter a limit merely because a parent is named on the teen's profile. Verify the cardholder or obtain authority supported by the account records and applicable procedures. If authority cannot be established with the available information, do not disclose or change the teen card; explain the limitation and use the appropriate human-transfer route if further handling is needed.

## Tool workflow

1. **Identify and verify the person.**
   - Use `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id` to locate a profile only as needed.
   - Obtain and compare two identity fields; then call `get_current_time` and `log_verification` with all required recorded fields and that timestamp.
   - Treat each cardholder separately where cards belong to different users.

2. **Retrieve each affected checking account and its cards.**
   - Unlock and call `get_all_user_accounts_by_user_id_3847` using the authorized user's `user_id`.
   - Select checking accounts only. For each relevant account, unlock and call `get_debit_cards_by_account_id_7823` with the `account_id`.
   - Match the card by cardholder and the customer's unambiguous description. Never select a historical CLOSED card when an ACTIVE card is intended.

3. **Check the decline in the documented order.** For every affected card, inspect:
   1. Card status. A temporary limit increase requires `ACTIVE`.
   2. Linked checking-account status. It must be `OPEN`.
   3. Fraud-alert status and source. A bank-initiated fraud alert must not be cleared by the agent; transfer to security with `fraud_or_security_concern`. A customer-initiated alert can only be cleared after required identity verification and confirmation of legitimate transactions.
   4. Velocity-block status. It expires automatically after 30 minutes; early clearing requires identity verification and the documented velocity-block procedure. Do not clear one merely to test an ATM decline.
   5. PIN lock status. If PIN-locked, stop this workflow for that card and follow the PIN Lock Investigation Protocol; do not unlock it or attribute the decline to the ATM limit.

4. **Assess limit, available funds, and activity.**
   - Use the debit-card lookup's `daily_atm_limit` and `daily_atm_used` to calculate `remaining = max(limit - used, 0)`. If daily usage is not returned, say that remaining ATM capacity cannot yet be determined; do not substitute a product-level default.
   - Unlock and call `get_bank_account_transactions_9173` for each linked account. Review pending debits and posted activity along with the current account balance, because pending authorizations and transactions can reduce available funds.
   - A withdrawal greater than remaining capacity supports a limit-related explanation, but it is not conclusive if the card/account/security checks or available funds show another cause.
   - If several otherwise eligible cards fail at the same ATM, a common ATM/operator or network issue is plausible. Do not claim that it is confirmed. Explain that trying a different ATM or an alternate way to pay may help; a third-party ATM may impose a lower limit that Rho-Bank cannot override.
   - A PIN being accepted only shows that PIN validation reached that stage; it does not establish that the account had funds, that a limit was available, or that the terminal was usable.

5. **Report the diagnosis clearly.** For each verified, authorized card, provide the current ATM limit, amount used if available, remaining amount if calculable, and the most specific supported reason or next check. Avoid exposing internal fraud rationale. If the source is unknown, say so rather than presenting a limit as the cause.

6. **Offer a temporary increase only when appropriate.** A request to *check* a limit is not consent to change it. Before submitting an increase, obtain the cardholder's explicit consent and a specific requested **new daily ATM limit**. Explain that an approved temporary increase lasts 24 hours and then automatically reverts, and that it cannot bypass a third-party ATM's own limit.

   Verify all of the following for the selected card and linked checking account:
   - Account status is `OPEN` and it is a checking account.
   - Account has been open at least 60 days.
   - No `overdraft_fee` transactions occurred in the prior 30 days.
   - Card status is `ACTIVE`.
   - Requested new limit is positive and no more than 150% of the card's current ATM limit.
   - No other temporary increase was made for that card in the previous 24 hours.

   Use `scripts/evaluate_atm_limit.py` for the date, overdraft, remaining-capacity, and 150% calculations. The executor must obtain the 24-hour frequency fact from an available card/request-history result or an authoritative response from the limit-request workflow. If that fact cannot be established, do not state the request is eligible or represent it as approved. Do not fabricate a tool parameter or a history lookup that is not available.

7. **Submit only a valid, authorized request.** Unlock `request_temporary_debit_card_limit_increase_8374`, then call it through `call_discoverable_agent_tool` with exactly:
   - `card_id`: selected active debit card ID
   - `limit_type`: `"atm"`
   - `new_limit`: the explicit requested new daily limit

   Interpret the actual tool response as authoritative. Confirm approval only after a successful response. If declined, report the applicable supported reason and do not retry with altered values without a new, authorized customer request. A tool or system failure that prevents an otherwise valid request may be transferred with `technical_system_error` and a concise summary.

## Calculation helper

`scripts/evaluate_atm_limit.py` accepts one account/card pair on JSON stdin and emits a JSON assessment on stdout. It uses only Python's standard library and makes no banking changes.

Input schema:

```json
{
  "as_of": "runtime current timestamp",
  "account": {
    "status": "OPEN or other status",
    "account_type": "checking or other type",
    "date_opened": "MM/DD/YYYY or ISO date"
  },
  "card": {
    "status": "ACTIVE or other status",
    "daily_atm_limit": "current numeric limit",
    "daily_atm_used": "current numeric usage, optional"
  },
  "transactions": [
    {"date": "MM/DD/YYYY or ISO date", "type": "transaction type", "status": "posted or pending"}
  ],
  "attempt_amount": "attempted withdrawal amount, optional",
  "requested_new_limit": "customer-authorized new daily limit, optional",
  "temporary_increase_in_last_24h": true
}
```

Use `null` for an unknown `temporary_increase_in_last_24h`; never replace unknown data with `false`. A runnable invocation is `python scripts/evaluate_atm_limit.py`, with an object conforming to the schema supplied on standard input. The output contains `checks`, `diagnosis`, `approval_status`, monetary calculations as two-decimal strings, and `missing_data`. An `approval_status` of `eligible` is only a calculation result; it does not approve or submit a banking request.

## Failure handling and boundaries

- If records cannot be matched to a verified person, request clarifying information without disclosing candidate account details.
- If an account is not OPEN, a card is not ACTIVE, the account is too new, an overdraft fee exists in the 30-day window, the requested limit exceeds 150%, or a prior increase exists in 24 hours, do not call the increase tool.
- If a bank-initiated fraud alert exists, transfer to the security team; do not attempt to clear it.
- If the user demands an action unsupported by the available verified data, explain what remains necessary. Use `other` with a detailed summary only when a transfer is genuinely required and no higher-priority transfer reason applies.
- Never promise that an ATM will dispense cash after a Rho-Bank limit increase. Third-party ATM constraints remain independent.
