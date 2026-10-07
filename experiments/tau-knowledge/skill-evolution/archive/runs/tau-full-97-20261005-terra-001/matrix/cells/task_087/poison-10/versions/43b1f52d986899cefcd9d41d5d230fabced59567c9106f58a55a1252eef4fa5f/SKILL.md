---
name: debit-card-code-05-and-fraud-dispute
summary: Investigate one or more debit-card CODE 05 / Do Not Honor declines for a verified customer, including frozen-card recovery, fraud-alert handling, and a safe handoff or debit-card dispute workflow when an unauthorized transaction is reported.
---

# Debit-card CODE 05 investigation and fraud-dispute workflow

Use this Skill when a verified customer reports one or more debit-card declines showing **CODE 05 (Do Not Honor)**, particularly if reviewing the declines reveals an active fraud alert or an unauthorized transaction.

Do not assume that multiple declined cards have the same cause. Review each affected card separately and keep the customer informed without exposing full card numbers or unrelated account details.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow, do not disclose account or card information, clear a protection, unfreeze a card, file a dispute, close a card, or transfer account details until:

1. The customer has been uniquely identified.
2. At least two supplied identity fields match the selected profile.
3. `log_verification` has successfully recorded verification using the complete profile fields and a current timestamp.
4. The card belongs to the verified user and is linked to that user's checking account.

## Tools and tool access

Unlock documented specialized tools before calling them through `call_discoverable_agent_tool`:

- `get_all_user_accounts_by_user_id_3847` — `{"user_id":"..."}`
- `get_debit_cards_by_account_id_7823` — `{"account_id":"..."}`
- `get_bank_account_transactions_9173` — `{"account_id":"..."}`
- `clear_debit_card_fraud_alert_4892` — `{"card_id":"...","reason":"customer_verified"}` or `{"card_id":"...","reason":"velocity_clear"}`
- `unfreeze_debit_card_3893` — `{"card_id":"..."}`
- `file_debit_card_transaction_dispute_6281` — use only after every required dispute field and pre-filing condition is established.

Use `transfer_to_human_agents` directly for an escalation. Use only documented arguments and never invent tool results, transaction identifiers, amounts, dispute-limit results, or eligibility decisions.

## 1. Identify and verify

1. Resolve the caller's name, email, user ID, or address to exactly one profile. If a name produces multiple profiles, request a distinguishing identifier and do not choose by name alone.
2. Compare at least two caller-provided fields against that profile, such as date of birth, email, telephone number, or address.
3. Retrieve the current time and call `log_verification` with the complete matching profile data and timestamp.
4. If matching data is insufficient, conflicting, or ambiguous, do not access banking records or take banking action.

## 2. Collect all checking accounts and cards

1. Retrieve all accounts for the verified `user_id`.
2. Select every account whose type is checking, regardless of whether the customer identified a particular card.
3. Retrieve debit cards for **each** checking account. A checking account may return current and historical cards.
4. For every returned card, confirm that its `user_id` equals the verified user and that its `account_id` is one of the retrieved checking accounts. Do not disclose or act on a mismatch. If resolution requires a human, transfer using `account_ownership_dispute`.
5. Preserve, per card: card ID, last four digits, status, issue reason, linked account status, fraud-alert status/source, and velocity-block status.

Run `scripts/evaluate_code05.py` after records are collected if useful. It produces an advisory ordering plan only; it does not authorize a banking action.

## 3. Diagnose each reported CODE 05 card in order

For each card the customer reports as declined, perform the checks in this exact order. Do not skip from a card-status finding to fraud or velocity processing. A decisive condition may require a separate workflow for that card.

### A. Card status

- **FROZEN:** Ask whether the customer wants it unfrozen. Unfreeze only after the customer explicitly agrees, ownership is confirmed, and the linked checking account is `OPEN`. Call `unfreeze_debit_card_3893` and confirm success only from its result.
- **CLOSED:** Explain that it is no longer active. Check for another active card or discuss replacement; never reactivate the closed card.
- **PENDING:** It requires activation. Before activation, verify physical possession, an open linked account, non-expiration, matching last four digits/expiration/CVV, and a compliant customer-selected PIN. Select the documented activation tool by issue reason.
- **ACTIVE:** Continue to linked-account status.
- **Missing or unrecognized status:** Obtain corrected information; do not infer a decline cause.

### B. Linked checking-account status

For an active card, inspect its linked account.

- If the account is not `OPEN`, do not disclose the details of a `SUSPENDED` or `RESTRICTED` account. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
- Only an `OPEN` linked account proceeds to alert and velocity checks.

### C. Fraud alert

- If the alert is active and `alert_source` is `customer_initiated`, ask the customer to verify recent transactions.
  - Clear it only when the verified customer confirms the reviewed transactions are legitimate, agrees to removal, and the card belongs to them. Call the clear tool with `reason: "customer_verified"` and document why.
  - If the customer reports any transaction as unauthorized or suspicious, **do not clear the alert**. Preserve the alert and begin the fraud/dispute workflow below.
- If the alert is bank-initiated, never attempt to clear it. Explain that a security review is required and transfer using `fraud_or_security_concern`.
- If an active alert lacks a recognized source, do not clear it. Escalate for security review with `fraud_or_security_concern`.

### D. Velocity block

Only after the alert check is safely complete:

- If `velocity_blocked` is true, explain that unusual activity temporarily blocked the card and the block automatically lifts after 30 minutes. Offer an early lift.
- Clear early only when verification and ownership are established, the customer asks for it, and gives a reasonable explanation for the activity. Call the clear tool with `reason: "velocity_clear"` and document the reason.
- If none of the ordered checks explains the decline, collect the merchant type, transaction timestamp, error text, screenshots if available, and device/app/browser details. Do not promise a retry will succeed.

## 4. Unauthorized debit-card transaction: investigation and dispute path

This section applies whenever the customer says a transaction is unauthorized, whether it arises during the CODE 05 review or independently. Do not state that dispute guidance is unavailable: a documented debit-card dispute procedure exists.

### Preserve the security protection and retrieve the transaction

1. Keep the fraud alert active after an unauthorized-transaction report. Never use a customer-verified alert clearing to resolve a reported fraud transaction.
2. Identify the card's linked **open checking account**.
3. Retrieve its transaction history with `get_bank_account_transactions_9173(account_id)`.
4. Locate the reported transaction from the customer-provided date, merchant/description, location, and other facts. Record its exact `transaction_id`, date, amount, type, and posted/pending status from the returned record.
5. If no unique transaction is found, ask focused clarifying questions; never substitute a guessed transaction ID, date, or amount.

### Gather and validate dispute facts

Before filing, explain the applicable Regulation E reporting timeframes: report within two business days of the statement for a maximum $50 liability, within 60 days for a maximum $500 liability, and later reports may have unlimited liability. Then obtain or confirm:

- the date the customer first noticed the transaction (`discovery_date`);
- that the transaction amount is at least $1 and the transaction is no more than 60 days old;
- the verified user, linked open checking account, card ID, exact transaction ID/date/amount, and that the account's open-dispute tier limit is not exceeded;
- whether the physical card remains in the customer's possession;
- whether the PIN was shared, observed/skimmed, not compromised, or is unknown;
- whether the transaction was an in-store PIN purchase, in-store signature purchase, online purchase, ATM activity, recurring payment, or person-to-person transaction;
- whether the merchant was contacted when the matter is a non-fraud dispute;
- whether a police report was filed when an actual fraud-dispute amount exceeds $500. If not, recommend one;
- whether the customer agrees that the conversation may serve as the written statement describing what happened.

For a transaction the customer did not make, first determine whether fraud is suspected. Use:

- `card_present_fraud` only for suspected physical/in-store card fraud;
- `card_not_present_fraud` only for suspected online/telephone fraud;
- `unauthorized_transaction` only when fraud is not suspected, such as an unapproved family-member charge.

A customer retaining the physical card, being elsewhere than the purchase location, and not having a compromised PIN can support suspected physical-card fraud, but do not infer whether a transaction was PIN or signature without supported facts.

Use `scripts/validate_debit_dispute.py` to validate gathered facts and choose conservative metadata. It does not determine dispute-limit status, provisional-credit eligibility, or authorization to file.

### File only when all prerequisites are known

Call `file_debit_card_transaction_dispute_6281` only after all documented pre-filing requirements and every required tool argument are established. Supply the exact values from records and customer responses. Do not guess `provisional_credit_eligible`; determine it under the documented provisional-credit guidelines. If the applicable guideline, dispute-limit information, or another required fact cannot be obtained using documented resources, preserve the information gathered and escalate instead of submitting an incomplete filing.

Set `card_action` according to the dispute category:

- `card_present_fraud` or `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- the documented non-fraud merchant/ATM categories → `keep_active`

`card_action` is dispute metadata. Any separate physical card closure, freeze, or reissue must independently satisfy its own documented prerequisites; do not claim it occurred unless its separate tool action succeeds.

## 5. Transfer and handoff

An unauthorized debit-card charge, active fraud alert, suspected fraud, or required fraud specialist is a Tier 1 security matter. If escalation is required or the customer requests specialist handling, call:

```json
{
  "reason": "fraud_or_security_concern",
  "summary": "Verified customer reports an unauthorized [location] debit-card charge on the [account/card nickname] card. Fraud alert remains active. Include exact transaction ID/date/amount if retrieved, card possession, customer location at the time, PIN status, discovery date, written-statement consent, police-report status if applicable, and all actions already completed."
}
```

Select the highest applicable transfer reason. Do **not** use `specialized_department_required` for an unauthorized transaction or active fraud-alert matter. Confirm transfer only after a successful tool result.

## Helper-script interfaces

### CODE 05 planner

`scripts/evaluate_code05.py` accepts JSON on stdin:

```json
{"user_id":"verified-user-id","accounts":[{"account_id":"checking-id","account_type":"checking","status":"OPEN"}],"cards":[{"card_id":"card-id","account_id":"checking-id","user_id":"verified-user-id","status":"ACTIVE","fraud_alert_active":false,"velocity_blocked":false}]}
```

It emits JSON with `valid`, `errors`, `analyzed_card_count`, `ignored_cards`, and per-card ordered findings. Validate `valid` and ensure every relevant checking card was included.

### Dispute validator

`scripts/validate_debit_dispute.py` accepts the collected dispute facts described in its module documentation. It emits `valid`, `errors`, `recommended_dispute_category`, `recommended_card_action`, and a filing-ready `arguments` object when all non-policy fields are present. Review it against account dispute limits and provisional-credit rules before any filing.
