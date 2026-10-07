---
name: debit-card-code-05-diagnosis
description: Diagnose one or more debit-card “CODE 05 / Do Not Honor” declines by applying the required card-status, linked-account, fraud-alert, and velocity-block checks in order. Use when a verified customer reports debit-card declines and requests investigation or resolution.
---

# Debit Card CODE 05 / Do Not Honor Diagnosis

Use this workflow for each debit card reported as declined. A CODE 05 is a generic decline; do not assume insufficient funds, fraud, or a block before retrieving the relevant records.

## Mandatory control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

In particular, do not clear a security protection, freeze/unfreeze a card, activate a card, order a card, or modify profile data until the required identity and ownership checks have been completed.

## Inputs and assumptions

Collect or use the conversation context to obtain:

- The affected customer/profile, resolving ambiguous same-name matches using an email address or mailing address.
- Whether identity has been verified. Verification requires confirmation of at least two of date of birth, email, phone number, and address, followed by `log_verification` with all required profile fields and a current timestamp.
- Each affected card or, if card details are unavailable, the linked checking accounts and the merchant/approximate decline time.
- Whether the customer recognizes recent activity and whether the declines were simultaneous or separate.

A customer statement alone does not replace record checks. If the customer cannot be identified or verification/ownership cannot be established, do not take a banking action; explain what is needed or escalate when appropriate.

## Runtime tools

Use the normal banking tools supplied by the runtime. Where a named internal tool is not directly exposed, unlock it with `unlock_discoverable_agent_tool` and invoke it through `call_discoverable_agent_tool` using a JSON-string `arguments` value.

Relevant internal tools documented for this workflow are:

- `get_all_user_accounts_by_user_id_3847(user_id)` — retrieve checking and savings accounts, including account ID, type, status, and balance.
- `get_debit_cards_by_account_id_7823(account_id)` — retrieve debit cards for a checking account.
- `clear_debit_card_fraud_alert_4892(card_id, reason)` — clear an eligible customer-initiated fraud alert or velocity block only after verification.
- `freeze_debit_card_3892(card_id)` and `unfreeze_debit_card_3893(card_id)` — use only when the card workflow and prerequisites support the requested action.

For example, the discoverable invocation shape is:

```text
unlock_discoverable_agent_tool(agent_tool_name="get_all_user_accounts_by_user_id_3847")
call_discoverable_agent_tool(
  agent_tool_name="get_all_user_accounts_by_user_id_3847",
  arguments='{"user_id":"<verified-user-id>"}'
)
```

Do not treat an unlock as an action on the customer’s account. Treat a tool result, including an empty result or error, as evidence to communicate or investigate; never fabricate fields or a successful action.

## End-to-end procedure

1. **Resolve and verify the customer.**
   - If several profiles match a name, ask for an identifying detail and use the matching profile; do not merge profiles.
   - Confirm at least two identity fields with the customer. Obtain the current time with `get_current_time`, then call `log_verification` using the verified customer’s complete required profile fields and the timestamp.
   - Confirm the customer owns the affected debit cards/accounts before any card action.

2. **Discover the relevant checking accounts and cards.**
   - Retrieve all accounts for the verified user using `get_all_user_accounts_by_user_id_3847`.
   - Limit debit-card lookups to checking accounts. For every relevant checking account, retrieve its cards with `get_debit_cards_by_account_id_7823`.
   - Match the customer’s affected cards when possible using last four digits, merchant/time details, or the customer’s description. If the customer says several cards declined, investigate every identified affected card rather than stopping after the first result.
   - Record each card ID, last four digits, card status, linked account ID/status/balance, and any fraud-alert or velocity-block fields returned. If the lookup response lacks a field required for diagnosis, state that the issue cannot yet be conclusively diagnosed and use only supported escalation or follow-up paths.

3. **Apply CODE 05 checks in this exact order for each affected card.**

   **A. Card status**
   - `FROZEN`: ask whether the verified owner wants it unfrozen. Before unfreezing, ensure the linked checking account is `OPEN`; then use the documented unfreeze tool and confirm success. If the customer does not consent, explain that new transactions remain declined.
   - `CLOSED`: explain that the card is no longer active. Check for another active card; otherwise offer the supported replacement path without claiming a replacement was ordered unless the appropriate tool succeeds.
   - `PENDING`: explain that the card is not activated. Use the activation workflow only if the customer requests it and all activation prerequisites are met, including physical possession, matching card details, pending status, open linked checking account, non-expiration, and the correct activation tool for its issue reason.
   - `ACTIVE`: continue to the account check.

   **B. Linked checking-account status**
   - If the linked checking account is not `OPEN`, do not disclose specific restriction details for `SUSPENDED` or `RESTRICTED` accounts. Tell the customer exactly: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
   - Do not proceed to a card security clear for an account that is not open.
   - If the account is open, continue to the fraud-alert check. A displayed balance alone is not proof that sufficient funds were available at authorization; pending holds may reduce available funds.

   **C. Fraud alert**
   - If `fraud_alert_active` is false, continue to the velocity check.
   - If it is true with source `customer_initiated`, ask the verified customer to review/confirm that recent transactions are legitimate. Only after that confirmation may the agent clear it using `clear_debit_card_fraud_alert_4892` with `reason` set to `customer_verified`. Document the reason in the interaction summary.
   - If it is true with source `bank_initiated`, never attempt to clear it. Tell the customer: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Then call `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise factual summary.
   - If the customer reports unrecognized transactions, do not clear an alert; escalate to security.

   **D. Velocity block**
   - If `velocity_blocked` is false, the ordered security checks are complete.
   - If true, explain: “Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?”
   - Because identity must already be verified, obtain the customer’s consent and a reasonable explanation for the activity, then call `clear_debit_card_fraud_alert_4892` with `reason` set to `velocity_clear`. Confirm only the tool result. If the customer declines or prerequisites are not met, advise waiting for the automatic expiry.

4. **Assess unresolved active/open cards after the ordered checks.**
   - Explain that CODE 05 remains a generic decline when no status, account restriction, fraud alert, or velocity block is found.
   - Consider supported non-sensitive causes such as insufficient available balance, pending holds, or a merchant submitting an amount higher than initially estimated. Do not assert one of these occurred without supporting data.
   - Advise the customer to review recent and pending activity, add funds if appropriate, and ask the merchant to confirm the authorization amount. For detailed posted/pending transaction history, direct the customer to the mobile app/online banking or the documented support channel.
   - Capture card identifier/last four, merchant, timestamps, decline code, and observed status results. If repeated attempts give the same result, gather device/browser/app version and screenshots when applicable, then escalate with logs using the applicable supported transfer reason (normally `technical_system_error` if no fraud/security concern is present).

5. **Conclude clearly.**
   - Summarize every affected card separately: what was checked, any action actually completed, and the next step.
   - Do not say a card or account is usable until the relevant tool has confirmed the change or the observed status supports that statement.
   - Never expose full card numbers, security-sensitive restriction details, or another profile’s data.

## Validation checklist

Before responding or transferring, confirm:

- The correct customer profile was selected and identity verification was logged before any banking action.
- All identified affected debit cards were investigated.
- For each card, checks followed card status → linked account status → fraud alert/source → velocity block.
- No bank-initiated fraud alert was cleared, and every security clear used the exact allowed reason.
- Any unfreeze occurred only with owner consent, a frozen card, and an open linked checking account.
- The response distinguishes confirmed tool results from possible generic-decline causes and gives a concrete next step for every unresolved card.
