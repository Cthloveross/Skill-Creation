---
name: debit-card-code-05-triage
description: Investigate one or more debit-card CODE 05 (“Do Not Honor”) declines in the required card-status, account-status, fraud-alert, and velocity-block order. Use for debit-card decline diagnosis and permitted card-security remediation.
---

# Debit Card CODE 05 Triage

Use this Skill for debit-card CODE 05 declines, including several cards or merchants. Treat each physical card as a separate case; do not assume multiple declines have one cause.

## Safety and prerequisites

Before any action that changes a card or account:

1. Verify the customer using the supported identity-verification procedure and create the required audit record with `log_verification`. The runtime requires confirmation of at least two profile fields. Obtain the current time with `get_current_time` for `time_verified`.
2. Confirm authority and ownership: the identified card's `user_id` must match the verified customer and the linked checking account must be the intended account.
3. Identify the exact card. Prefer its last four digits. An account nickname can narrow an account lookup but is not, by itself, a reliable card identifier; confirm the returned card with the customer before an action.
4. Before remediation, check the card/account status and all action-specific requirements. Obtain explicit customer consent before unfreezing a card or clearing a security protection.
5. Never disclose internal fraud codes, a bank-initiated fraud reason, or detailed account-restriction information. Never attempt to clear a bank-initiated fraud alert.

A prior identity conversation is not an audit record by itself. If a valid verification record was not logged during the current interaction, log it before performing a card action.

## Available lookup workflow

The ordinary runtime may not expose debit-card and bank-account lookups directly. Obtain documented specialized tools through the discoverable-agent mechanism:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name: "get_all_user_accounts_by_user_id_3847"`.
2. Call `call_discoverable_agent_tool` with that name and JSON `arguments` containing the verified `user_id`.
3. From that response, identify relevant checking account IDs. For each, unlock `get_debit_cards_by_account_id_7823` and call it with `{"account_id":"..."}`.
4. Match the selected card, then confirm the returned `user_id` and `account_id` before any action.

Account-ID acquisition is necessary before account-specific card retrieval. It is not a conclusion about linked-account status. When investigating multiple known accounts, complete the needed debit-card lookups before giving a customer-facing diagnosis, promising usability, or taking a remedy. Do not infer that a debit card is absent from empty credit-card results; credit cards are a different product.

If a required lookup cannot be unlocked or lacks required fields, do not guess a status or clear a protection. Explain that diagnosis cannot yet be completed. Use `technical_system_error` only for an actual runtime/system failure that prevents completion and requires transfer.

## Required CODE 05 sequence

Perform this sequence for every confirmed card. Inspect and communicate results in this order; do not skip a prerequisite. A returned card record can expose several fields at once, but do not communicate a later-stage conclusion until the prior stages have been assessed.

### 1. Card status

Inspect `status` first.

- `FROZEN`: ask whether the customer wants it unfrozen. Unfreeze only after verified identity, ownership, confirmation that the linked checking account is open, and affirmative consent. Unlock and call `unfreeze_debit_card_3893` with `card_id`, then confirm the tool result. After the freeze is resolved, continue the remaining applicable CODE 05 checks; unfreezing does **not** clear a fraud alert or velocity block.
- `CLOSED`: explain that the card is no longer active. Check for another active card or discuss replacement. Do not order a replacement until eligibility, fees, delivery/design choices, balance, and confirmation requirements are checked.
- `PENDING`: the card has not been activated. Follow the activation workflow, including physical-card possession, matching last four digits/expiration/CVV, acceptable PIN, open account, and issue-reason-specific activation tool selection.
- `ACTIVE`: continue to linked-account status.
- Missing or unfamiliar status: stop this card's diagnosis and obtain reliable card information.

Do not say a formerly frozen card is ready to use merely because the unfreeze succeeded. It may still have a security protection found during this CODE 05 diagnosis.

### 2. Linked checking-account status

For an active card, inspect the linked checking account.

- If it is not `OPEN`, do not disclose detailed restriction information, particularly for suspended or restricted accounts. Tell the customer: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Stop this card's CODE 05 path.
- If it is `OPEN`, continue to fraud-alert status.
- If no linked-account status is available, do not proceed as though it were open.

### 3. Fraud alert

For an active card with an open linked account, inspect `fraud_alert_active` and `alert_source`.

- If no fraud alert is active, continue to velocity-block status.
- For a customer-initiated alert, ask the customer to verify recent transactions. Clear it only after identity is verified, ownership is confirmed, the customer confirms all relevant transactions are legitimate, and the customer consents. Use `clear_debit_card_fraud_alert_4892` with `reason: "customer_verified"`, and document why it was cleared.
- If the customer reports any transaction as unauthorized or suspicious, leave the alert in place. Do not treat that report as a legitimacy confirmation. Transfer to the security team with `transfer_to_human_agents` using `reason: "fraud_or_security_concern"` and a concise factual summary.
- If the alert is bank-initiated, do **not** clear it. State: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Transfer with `reason: "fraud_or_security_concern"`.
- If an alert is active but its source is absent or unrecognized, do not clear it; obtain the source or use security escalation where appropriate.

### 4. Velocity block

For an active card with an open account and no unresolved fraud alert, inspect `velocity_blocked`.

- If `true`, explicitly tell the customer that unusual activity patterns caused a temporary velocity block, that it **automatically lifts after 30 minutes**, and offer an early lift after identity verification. Use clear customer-facing language such as: “Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?”
- This disclosure is required even if the card was also frozen and has been unfrozen. Make it before claiming the card can process normally. The card must not be represented as usable until the velocity block expires or is successfully cleared.
- Clear it early only after verified identity, confirmed ownership, a reasonable explanation for the unusual activity, and explicit consent. Unlock and call `clear_debit_card_fraud_alert_4892` with `card_id` and `reason: "velocity_clear"`. Document the rationale in the interaction notes.
- If `false`, the mandatory CODE 05 checks have not found a status/security cause. Do not invent a cause. Capture merchant, date/time, amount, card ending, device/channel, screenshots or exact error, and repeated-attempt details. Escalate with logs if repeated errors persist.

## Multiple-card handling

Maintain a case list containing merchant/context, confirmed card ending, `card_id`, linked account, observed fields, completed checks, consent, action taken, and outcome. Complete each card's ordered diagnosis before its conclusion. A security escalation for one card is not authorization to alter another card.

## Optional deterministic planning helper

`scripts/code05_plan.py` converts normalized lookup facts into a non-executing ordered plan. It never calls banking tools and a proposed action is not a completed action.

Input JSON schema:

```json
{
  "identity_verified": true,
  "cards": [
    {
      "label": "customer-provided case label",
      "card_id": "optional-card-id",
      "status": "ACTIVE|FROZEN|CLOSED|PENDING",
      "account_status": "OPEN|...",
      "fraud_alert_active": false,
      "alert_source": "customer_initiated|bank_initiated",
      "velocity_blocked": false,
      "transactions_confirmed_legitimate": false,
      "customer_consents_to_clear": false,
      "customer_requested_early_velocity_lift": false,
      "reasonable_velocity_explanation": false
    }
  ]
}
```

Only fields required by the reached stage are required. Booleans may be JSON booleans or strings `true`/`false`.

Example runtime call:

```text
run_skill_script(relative_path="scripts/code05_plan.py", input_json={"identity_verified":true,"cards":[...]})
```

The script emits JSON containing top-level `validation_errors`, one ordered result per card, `checked_in_order`, a non-executing `next_step`, action eligibility, and a required velocity-block notice where applicable. Before acting, verify that required live lookup fields are present, no result stopped at an unresolved stage, and the live card/account still matches the planned case.
