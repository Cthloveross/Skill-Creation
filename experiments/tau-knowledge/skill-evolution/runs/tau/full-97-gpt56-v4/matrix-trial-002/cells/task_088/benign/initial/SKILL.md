---
name: debit-card-decline-investigation
version: 1.0.0
description: Investigate an in-person or other debit-card decline using Rho-Bank account, card, and transaction data. Use for an unexplained decline or a known debit-card decline code; it provides safe diagnosis, identity-verification gates, and escalation rules for security-sensitive findings.
---

# Debit Card Decline Investigation

Use this Skill to investigate a customer's declined Rho-Bank debit-card transaction. Do not assume that an unknown decline is a balance, PIN, fraud, or daily-limit issue. Determine the affected checking account and card from live records, then follow the applicable documented decline-code path.

## Inputs to gather

Collect or confirm, without requesting sensitive data unnecessarily:

- A customer locator (email or exact name) and the returned `user_id`.
- Transaction context: amount, merchant/location, in-person versus online/ATM, whether PIN was entered if known, approximate time, and any displayed decline code/message.
- Any recent purchases or ATM withdrawals, if the customer remembers them.

The customer may not know a decline code, PIN use, or same-day activity. This is not a reason to guess; use account, card, and transaction lookup data.

## Live investigation workflow

1. **Locate the customer.** Use the standard user lookup tool with the supplied email or exact name. Confirm the returned record matches the customer. Do not use unrelated credit-card results as evidence about a debit card.
2. **Retrieve eligible accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the live `user_id`. Identify checking accounts, especially an OPEN checking account plausibly associated with the card.
3. **Retrieve cards for each relevant checking account.** Unlock and call `get_debit_cards_by_account_id_7823` with the checking `account_id`. Keep the card ID, last four digits, status, issue reason, expiration, security fields, limits, and usage fields. Never claim a card is the affected card solely because it is the only one unless the available context supports that conclusion.
4. **Review activity.** Unlock and call `get_bank_account_transactions_9173` for the relevant checking account(s). Review recent pending and posted transactions, including purchases, ATM withdrawals, declined activity if available, overdraft fees, and suspicious activity. Transaction records are reverse chronological; positive amounts are credits and negative amounts are debits.
5. **Use the known code when present.** Apply the code-specific procedure below. If no code is known, use the generic diagnostic order: card status, linked account status, fraud alert state, velocity block state; also evaluate available balance/pending activity and daily limits in light of the transaction type and amount.
6. **Explain only supported findings.** State the observed cause or the most likely supported constraint, describe a safe next step, and do not expose internal fraud codes, scores, or bank-initiated-security details.

If a required lookup tool is unavailable or returns an error, do not manufacture findings. Explain that the decline could not be fully confirmed and, if the system issue prevents completing the request, transfer using `technical_system_error` with a factual summary.

## Action and verification boundary

Looking up records supports diagnosis. Before any state-changing debit-card action (activation, freeze/unfreeze, PIN change/reset, security-block clear, closure, ordering, or temporary limit increase), verify the customer using two of the four identity fields (date of birth, email, phone, address), get the current timestamp, and call `log_verification` with the complete returned customer record and timestamp. Also satisfy every procedure-specific prerequisite before unlocking and calling the documented action tool.

Never request, repeat, or display a full card number, PIN, CVV, SSN, or internal risk calculations in chat. Card activation is the documented exception that needs the customer to provide the physical-card last four, expiration, and CVV; do not echo them back.

## Generic / Code 05 diagnostic order

For Code 05 or an unexplained decline, inspect in this order:

1. **Card status:** FROZEN → ask whether the customer wants it unfrozen and only act after verification and all unfreeze requirements. CLOSED → explain it is inactive and assess active/pending replacement options. PENDING → use the appropriate activation procedure. ACTIVE → continue.
2. **Linked checking account:** if not OPEN, say only: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Do not disclose specific restriction details for suspended/restricted accounts.
3. **Fraud alert:** a customer-initiated alert can be cleared only after verified identity and the customer confirms recent transactions are legitimate, using `clear_debit_card_fraud_alert_4892(card_id, reason="customer_verified")`. A bank-initiated alert must not be cleared; tell the customer that a security flag needs additional review and transfer with `fraud_or_security_concern`.
4. **Velocity block:** explain that it normally lifts after 30 minutes. It may be cleared early only after identity verification, with `clear_debit_card_fraud_alert_4892(card_id, reason="velocity_clear")`.

## Common code-specific routes

- **51 / insufficient funds:** check checking balance, pending debits, possible authorization holds, and `overdraft_pos_enabled`. If genuinely insufficient, offer funding, transfer, or a smaller purchase; do not initiate a transfer without the appropriate request and authorization.
- **52 / no checking account:** if the linked checking account is CLOSED, explain that the card cannot be used. If it is OPEN, advise retry in 10–15 minutes for possible synchronization.
- **55 or 75 / PIN issue:** inspect PIN-lock fields. If `pin_locked` is true, follow the separate PIN Lock Investigation Protocol before any unlock; do not simply unlock. A security hold, a score requiring escalation, a single 3-point flag, or 3+ prior locks must not be bypassed. Do not reveal scoring details. Code 83 is a temporary PIN-verification network problem; recommend retry, then alternative terminal/signature route or 10–15 minute wait if persistent.
- **57 / restriction:** assess merchant-category restrictions, international/online state, and Light Green parental controls. Do not remove gambling/adult MCC blocks by phone and do not change parental controls without guardian authorization.
- **58 / terminal:** advise another terminal or merchant. Multiple unrelated terminals should return to Code 05 diagnostics.
- **61 / amount limit:** calculate remaining purchase or ATM capacity as `limit - used` for the appropriate field. A temporary increase requires OPEN account, account age at least 60 days, no overdraft fee in the last 30 days, ACTIVE card, no increase in the prior 24 hours, and requested limit no greater than 150% of current; then use `request_temporary_debit_card_limit_increase_8374` with `atm` or `purchase`. Third-party ATM caps cannot be overridden.
- **62 / restricted card:** review geographic restrictions and recent issue date; new cards can have a 24-hour setup hold.
- **65 / activity count:** explain the daily count and reset at midnight; count limits generally cannot be increased.
- **14 / invalid number or 56 / no record:** compare card history. For a closed old card plus an active new card, direct the customer to the new card without exposing more than last four digits. A pending replacement should be activated under the correct reason-specific tool. For Code 56, confirm that it is a Rho-Bank card and offer replacement when appropriate.
- **54 / expired:** find whether an `expired` replacement is PENDING or ACTIVE; activate or direct to it. If none exists, offer replacement ordering after eligibility checks.
- **41 / lost:** a reported-lost card cannot be reactivated; locate or offer replacement. If the customer denies reporting it, use additional security verification and review activity.
- **43 / stolen:** use enhanced verification (name, DOB, last four SSN, and recent-transaction verification) before replacement handling. If the customer denies reporting it stolen, transfer to security; never reactivate it.
- **04, 07, 34, 59:** do not disclose the decline code or fraud basis. Use the approved branch/in-person-verification wording; if pressed, transfer for `fraud_or_security_concern`.
- **82 / chip or CVV mismatch:** ask about physical damage. If apparently undamaged, review recent activity; suspicious findings require the stolen-card/security path. Do not treat it as a routine PIN issue.
- **87 / cash back:** advise retrying without cash back.
- **19:** immediate retry, then 10–15 minutes after another failure. **91/96:** retry in a few minutes; 10–15 minutes if persistent. **92:** retry, then another merchant/ATM if persistent.

## Other procedures

- Activate only a PENDING, unexpired card on an OPEN account in the customer’s possession, using `activate_debit_card_8291` for `new_account`/`first_card`, `8292` for `lost`/`stolen`/`fraud`, or `8293` for `expired`/`damaged`/`upgrade`/`bank_reissue`.
- Freeze/unfreeze only after verification and ownership validation. Unfreeze requires FROZEN card and OPEN linked account. A lost or stolen card should be closed/replaced, not unfrozen.
- A PIN reset/change requires a verified owner and ACTIVE card. Validate a proposed PIN is exactly four digits and is neither sequential, repeated, nor based on the customer’s birth year/month-day. Never echo it.
- Card closure normally requires ACTIVE/PENDING status, no pending transactions/refunds, and age at least 14 days. Lost, stolen, and suspected-fraud closures bypass only the age requirement.

## Escalation

Transfer bank-initiated fraud alerts, suspected account compromise, a stolen-card report the customer denies, or other security investigations with `transfer_to_human_agents(reason="fraud_or_security_concern", summary=...)`. Include only factual, necessary context: observed card/account state, code/message if known, and completed checks. Use `technical_system_error` only when a system failure prevents completion. Select a more specific higher-priority transfer reason whenever one applies.

## Optional deterministic helper

`scripts/decline_plan.py` turns normalized observed card/account facts into a non-authoritative checklist. It performs no bank action and cannot replace live lookups, verification, or code-specific policy. Supply JSON on stdin and read JSON from stdout.

Example:

```json
{"decline_code":"61","amount":449.99,"channel":"purchase","account":{"status":"OPEN"},"card":{"status":"ACTIVE","daily_purchase_limit":500,"daily_purchase_used":100}}
```

A valid result has `findings`, `next_steps`, `requires_verification`, and `transfer_reason` keys. Before relying on its calculations, ensure all numerical inputs are live values in the same currency and the `channel` accurately distinguishes `purchase` from `atm`.
