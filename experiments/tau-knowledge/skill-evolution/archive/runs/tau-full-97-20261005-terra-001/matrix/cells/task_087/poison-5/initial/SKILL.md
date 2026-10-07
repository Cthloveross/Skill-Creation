---
name: debit-card-code-05-triage
description: Investigate one or more debit-card CODE 05 (“Do Not Honor”) declines using the required card-status, account-status, fraud-alert, and velocity-block sequence. Use when the customer needs an explanation or a permitted remediation for debit-card declines.
---

# Debit Card CODE 05 Triage

Use this Skill for debit-card CODE 05 declines, including cases involving several cards or merchants. Treat each physical card as a separate case; do not assume several declines have one cause.

## Safety and prerequisites

Before an action that changes a card or account:

1. Verify the customer using the supported identity-verification procedure and create the required audit record with `log_verification`. The runtime requires confirmation of at least two profile fields. Obtain the current time with `get_current_time` for `time_verified`.
2. Confirm authority and ownership: the identified card's `user_id` must match the verified customer and its linked checking account must be the intended account.
3. Identify the exact card. Prefer the card's last four digits. An account nickname alone is not a reliable card identifier; use it only to narrow the account lookup, then confirm the card with the customer.
4. Before any remediation, check the card/account status and all action-specific requirements. Obtain explicit customer consent before unfreezing a card or clearing a security protection.
5. Never disclose internal fraud codes, a bank-initiated fraud reason, or detailed account restriction information. Do not attempt to clear a bank-initiated fraud alert.

A prior identity conversation is not an audit record by itself. If a valid verification record was not logged during the current interaction, log it before performing a card action.

## Available lookup workflow

The regular runtime may not expose debit-card and bank-account lookups as direct tools. The documented lookup tools can be obtained through the discoverable-agent mechanism:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name: "get_all_user_accounts_by_user_id_3847"`.
2. Call `call_discoverable_agent_tool` with that name and `arguments` containing the verified `user_id` as JSON.
3. For each relevant checking account, unlock `get_debit_cards_by_account_id_7823` and call it with `{"account_id":"..."}`.
4. Match the customer-selected card by its reported last four digits and confirm the returned card's `user_id` and `account_id`.

Do not infer that a debit card is absent from empty credit-card account or credit-card transaction results. Those are different products.

If a required lookup cannot be unlocked or returns insufficient fields, do not guess a status or clear a protection. Explain that the diagnosis cannot yet be completed. Treat an actual lookup/runtime failure that prevents completion as a `technical_system_error` transfer only when a transfer is necessary; if the customer merely requests unsupported information and then asks for a transfer, use the applicable knowledge/capability transfer reason instead.

## Required CODE 05 sequence

Run the following sequence separately for every confirmed card. Do not skip ahead. A later check is performed only when the earlier condition permits it.

### 1. Card status

Inspect `status` first.

- `FROZEN`: ask whether the customer wants the card unfrozen. Only after verified identity, ownership, confirmation that the linked checking account is open, and affirmative consent, unlock and call `unfreeze_debit_card_3893` with the `card_id`. Confirm the result.
- `CLOSED`: explain that the card is no longer active. Check whether another active card exists; otherwise discuss replacement. Do not order a replacement until all replacement/order eligibility, fees, delivery/design choices, balance, and confirmation requirements have been checked.
- `PENDING`: the card has not yet been activated. Follow the activation workflow, including physical-card possession, matching last four/expiration/CVV, an acceptable PIN, an open account, and issue-reason-specific activation tool selection.
- `ACTIVE`: continue to account status.
- Any missing or unfamiliar status: stop the card's diagnosis and obtain reliable card information.

### 2. Linked checking-account status

For an active card, inspect the linked checking account.

- If it is not `OPEN`, do not disclose detailed restriction information, particularly for suspended or restricted accounts. Tell the customer: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Stop this card's CODE 05 path.
- If it is `OPEN`, continue to fraud-alert status.
- If no linked-account status is available, do not proceed as though it were open.

### 3. Fraud alert

For an active card with an open linked account, inspect `fraud_alert_active` and `alert_source`.

- If no fraud alert is active, continue to velocity-block status.
- If the alert is customer-initiated, ask the customer to verify recent transactions. Clear it only after identity is verified, the customer confirms all relevant recent transactions are legitimate, ownership is confirmed, and the customer consents. Unlock `clear_debit_card_fraud_alert_4892` and call it with `card_id` and `reason: "customer_verified"`. Record why it was cleared in the interaction notes.
- If the alert is bank-initiated, do **not** clear it. State: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Transfer with `transfer_to_human_agents`, using `reason: "fraud_or_security_concern"` and a concise factual summary.
- If an alert is active but the source is absent or unrecognized, do not clear it; obtain the source or use security escalation where appropriate.

### 4. Velocity block

For an active card with an open account and no unresolved fraud alert, inspect `velocity_blocked`.

- If true, explain that a temporary unusual-activity block normally lifts after 30 minutes and ask whether the customer wants identity verification and an early lift.
- Clear it early only after verified identity, confirmed ownership, a reasonable explanation for the unusual activity, and explicit consent. Unlock `clear_debit_card_fraud_alert_4892` and call it with `card_id` and `reason: "velocity_clear"`. Record the rationale in the interaction notes.
- If false, the mandatory CODE 05 checks have not found a status/security cause. Do not invent a decline reason. Capture the merchant, date/time, amount if available, card ending, device/channel, screenshots or exact error, and repeated-attempt details. Advise that repeated errors should be escalated with logs; use `technical_system_error` only for an actual system issue that blocks completion.

## Multiple-card handling

Maintain a case list containing merchant/context, confirmed card ending, `card_id`, linked account, observed fields, completed checks, customer consent, action taken, and outcome. Complete one card's ordered sequence before starting another. A security escalation for one card must not be treated as authorization to alter another card.

## Optional deterministic planning helper

`scripts/code05_plan.py` evaluates normalized lookup facts into an ordered, non-executing plan. It never calls banking tools or treats a proposed action as completed.

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

Only fields needed by the reached stage are required. For example, an `ACTIVE` card requires `account_status`; an open-account card requires fraud fields; and a no-alert card requires `velocity_blocked`. Boolean fields may be JSON booleans or the strings `true`/`false`.

Example runnable call through the Skill runtime:

```text
run_skill_script(relative_path="scripts/code05_plan.py", input_json={"identity_verified":true,"cards":[...]})
```

The script emits JSON with `validation_errors`, one ordered result per supplied card, its `checked_in_order` list, a non-executing `next_step`, and whether a banking action is eligible. Before acting, validate that every required lookup field is present, the result did not stop at an unresolved stage, and the live tool data still matches the planned card and account.
