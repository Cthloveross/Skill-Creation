---
name: debit-card-code-05-investigation
description: Investigate one or more debit-card purchase declines reported as CODE 05 / “Do Not Honor.” Use when a customer needs a status, linked-account, fraud-alert, velocity-block, or available-funds review, and safely perform or arrange permitted card remediation.
---

# Debit Card CODE 05 Investigation

## Purpose and scope

CODE 05 is a generic decline. Investigate each affected debit card in this exact order: **card status**, **linked checking-account status**, **fraud-alert fields**, then **velocity-block fields**. Do not infer that cards share an account or that a customer-reported previous freeze remains the cause; retrieve the relevant records.

This Skill covers debit cards and their linked checking accounts, not credit cards. If the customer reports a different decline code, use the procedure applicable to that code instead.

## Safety and prerequisite rules

Before any state-changing banking action, verify all applicable prerequisites: customer identity, authority and card ownership, product eligibility, linked-account status, card details, available balance or credit, fees, limits, cutoffs, recipient details where applicable, and required confirmation. Preserve these prerequisites in the interaction record.

For any card change or security-protection clearing:

1. Verify identity by confirming **two of four** fields held on the user profile: date of birth, email, phone number, and address.
2. Obtain the current timestamp with `get_current_time` and call `log_verification` with the full profile fields and timestamp after successful verification.
3. Confirm the customer owns the affected card and obtain explicit confirmation for the intended change.
4. Never expose full card numbers, fraud-detection logic, or internal decline codes that must not be disclosed.
5. Never clear a bank-initiated fraud alert. Do not repeat an action if a tool reports an unknown outcome.

Read-only lookup can be used to identify and investigate the customer’s records. Do not treat an unverified customer as authorized to freeze, unfreeze, activate, clear an alert/block, replace a card, or make another account/card change.

## Available runtime tools

The specialized tools below may need to be unlocked before calling them. Use `unlock_discoverable_agent_tool` with the exact name, then invoke it through `call_discoverable_agent_tool` using a JSON string for `arguments`.

- `get_all_user_accounts_by_user_id_3847` — input: `{"user_id":"..."}`. Returns all accounts, including ID, type, status, balance, and opening date.
- `get_debit_cards_by_account_id_7823` — input: `{"account_id":"..."}`. Returns debit cards for a checking account, including card ID, last four, status, issue reason, expiration, and relevant security fields when provided.
- `get_bank_account_transactions_9173` — input: `{"account_id":"..."}`. Returns reverse-chronological transaction history; use to assess recent posted/pending activity or explain authorization holds.
- `clear_debit_card_fraud_alert_4892` — input: `{"card_id":"...","reason":"customer_verified"}` to clear an eligible customer-initiated alert after verification and legitimacy confirmation, or `{"card_id":"...","reason":"velocity_clear"}` to clear a velocity block after verification and a reasonable explanation.
- `freeze_debit_card_3892` — use only for an owned, verified card currently `ACTIVE`, after explaining transaction effects and receiving confirmation.
- `unfreeze_debit_card_3893` — use only for an owned, verified card currently `FROZEN` with an `OPEN` linked checking account and customer confirmation.

Do not guess unsupported parameters. Follow the tool’s returned schema or error and report a safely bounded outcome.

## End-to-end workflow

### 1. Identify the customer and affected scope

1. Collect a user ID, email, or full name. If a name yields multiple profiles, request a disambiguator such as email or user ID before accessing a profile.
2. Establish the resolved user ID.
3. Ask which cards declined, which merchants and approximate times were involved, whether any were successful, whether the customer froze/reported cards lost or stolen, and whether there was recent unusual activity. These details help distinguish a status problem from a temporary security control, but do not replace record lookup.
4. Do not assume all reported cards belong to one checking account.

### 2. Retrieve accounts and cards

1. Unlock and call `get_all_user_accounts_by_user_id_3847` using the resolved user ID.
2. Select every checking account returned. Savings accounts do not have debit cards.
3. For each checking account, unlock if necessary and call `get_debit_cards_by_account_id_7823`.
4. Match cards using customer-provided last four digits when available. If the customer only knows that several cards declined, review all cards returned for their checking accounts while limiting disclosures to information appropriate for the account holder.
5. Maintain a per-card checklist so every affected card gets its own ordered CODE 05 review. Link each card to the account ID from the record, not an assumption.

### 3. Apply the ordered CODE 05 decision tree to each card

#### A. Card status (first)

- `FROZEN`: Explain that the card is temporarily locked. Ask whether the customer wants it unfrozen. If yes, complete identity verification, confirm ownership and that the linked checking account is `OPEN`, obtain confirmation, then use `unfreeze_debit_card_3893`. Confirm the resulting status only after the tool succeeds.
- `CLOSED`: Explain that the card is no longer active. Look for another active or pending card on the linked account. Offer appropriate replacement guidance if none exists; do not imply that a closed/lost/stolen card can be reactivated.
- `PENDING`: Explain that the card is not yet activated. Use the debit-card activation procedure rather than attempting an unfreeze or alert clear. Activation requires verified identity, physical possession, open account, unexpired pending card, matching last four/expiration/CVV, an acceptable non-sequential/non-repeating four-digit PIN, and the issue-reason-specific activation tool.
- `ACTIVE`: Continue to linked account status.
- Missing, ambiguous, or other status: do not make a card change; explain that further review is needed and obtain a supported escalation if necessary.

If a status branch fully explains the decline, still inspect the linked account when doing so is necessary to meet the stated prerequisite (for example, before unfreezing). For active cards, always continue through the remaining ordered checks.

#### B. Linked checking-account status (second)

- If the linked checking account is not `OPEN`, do not disclose whether the status is suspended or restricted. Tell the customer exactly: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Do not attempt card/security clearing to bypass the restriction.
- If it is `OPEN`, continue to fraud-alert review.

#### C. Fraud alert (third)

Inspect `fraud_alert_active` and `alert_source` from the debit-card lookup response.

- No active fraud alert: continue to velocity-block review.
- Active alert with `alert_source` `customer_initiated`: ask the customer to verify recent transactions. Only if the customer verifies identity and confirms the transactions are legitimate may you obtain confirmation and clear it with `clear_debit_card_fraud_alert_4892` using reason `customer_verified`. Record why it was cleared.
- Active alert with `alert_source` `bank_initiated`: do not clear it and do not attempt the clearing tool. Tell the customer: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Then call `transfer_to_human_agents` with `reason` `fraud_or_security_concern` and a concise factual summary.
- Alert source missing or not recognized: do not clear it; treat it as a security concern and escalate rather than assuming customer initiation.

#### D. Velocity block (fourth)

Inspect `velocity_blocked` from the lookup response.

- If false or absent, explain that no velocity block was identified and continue with balance/hold review if the card is active and account open.
- If true, explain: “Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?”
- Clear early only after identity verification, ownership confirmation, a reasonable explanation for the activity, and explicit customer confirmation. Call `clear_debit_card_fraud_alert_4892` with reason `velocity_clear`, then document the reason and result. Otherwise, advise waiting for automatic expiry.

### 4. Consider available funds and holds when status/security checks do not resolve the decline

For an active card with an open account and no blocking security condition, assess whether funds could explain the decline:

1. Obtain or review the checking account balance returned by account lookup; clarify that it may not equal available funds if authorization holds exist.
2. If appropriate, retrieve transactions using `get_bank_account_transactions_9173`. Pending activity and authorization holds can reduce usable funds even if a hold is not immediately displayed in recent transactions.
3. For Green Account checking, transactions that exceed available funds by more than the small permitted buffer are declined at authorization and do not create a negative balance. Do not promise overdraft coverage or an overdraft transfer.
4. Advise the customer to add funds or reduce/retry the payment only when lack of available funds plausibly explains the decline. Do not claim a precise available balance unless the supported tool provides it.

### 5. Close the interaction

Summarize separately for each affected card: linked account, reviewed status/security conditions, any completed action and its result, and safe next step. Do not claim a decline is resolved until the relevant tool confirms the change; a merchant may still need to submit a new authorization.

If the same unexplained problem persists after supported review, capture merchant/workflow details, timestamps, device/browser/app version when relevant, and exact error wording for escalation. Escalate security issues with `transfer_to_human_agents` using `fraud_or_security_concern`; use another supported transfer reason only when it more accurately describes the unresolved problem.

## Validation checklist

Before completing, confirm:

- The customer profile was disambiguated and the correct user ID was used.
- All checking accounts, rather than an assumed single account, were considered.
- Each affected card had card status, linked-account status, fraud alert, and velocity block evaluated in order.
- No state-changing tool was used before verification, ownership, prerequisites, and confirmation.
- Bank-initiated or unclear-source fraud alerts were not cleared and were escalated.
- Any unfreeze was limited to a frozen owned card with an open linked account.
- Any eligible clear used the correct reason value and was documented.
- The customer-facing response avoids sensitive internal security details and unsupported assurances.
