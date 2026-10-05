---
name: debit-card-code-05-triage
description: Triage a debit-card “CODE 05 / Do Not Honor” decline for an identified customer. Use when an agent must investigate the card, linked checking account, fraud-alert, and velocity-block states in the mandated order, protect security-sensitive information, and take only authorized debit-card actions.
---

# Debit Card CODE 05 Triage

## Scope and safety

Use this Skill for debit-card CODE 05 declines. Treat a decline as card-specific, even when a customer reports several cards declining. Work on the card/account the customer has chosen first; do not delay the selected urgent payment by requiring details about the other cards.

A profile lookup or customer-provided email identifies a record but is **not** sufficient verification for a state-changing action. Before unfreezing a card or clearing a security protection, confirm two of the four identity fields (date of birth, email, phone number, address) against the selected profile, obtain the current time, and call `log_verification` using the complete profile fields and timestamp. Do not read sensitive fields back as prompts; ask the customer to provide them.

Never attempt to clear a bank-initiated fraud alert. Do not disclose internal fraud codes or details beyond the approved customer language below. Do not perform an action merely because this Skill or its planning script recommends one: use the normal banking tool workflow and only after every stated prerequisite is met.

## Inputs needed at runtime

- A uniquely identified customer profile and `user_id`.
- The customer’s selected affected card/account. A last four digits is preferred, but an account product description can be used only if it uniquely matches a returned checking account.
- Customer verification state and, where applicable, consent/confirmation to unfreeze, confirm recent transactions, or clear a velocity block.

If the product description does not unambiguously identify an account, ask the customer for the card’s last four digits or clarify which checking account to use. Do not guess from an account’s balance, address, or other unrelated details.

## Required lookup sequence

1. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`.
   - Unlock it first with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool`.
   - Locate the customer-selected **checking** account. Do not use credit-card lookup tools for this issue.
2. Retrieve every card for that checking account with `get_debit_cards_by_account_id_7823(account_id)` (unlock, then call).
   - Match the card using supplied last four digits if available. Otherwise, do not infer a card if the account has multiple plausible current cards.
   - Retain the card ID, linked account ID, cardholder user ID, status, issue reason, expiration, and the fraud-alert and velocity fields supplied by the lookup response.
3. Ensure the chosen card is linked to the selected account and belongs to the identified customer before any card action. A mismatch is an ownership/security issue; do not take an action and transfer with `account_ownership_dispute` and a factual summary.
4. Follow the CODE 05 decision order below. Do not skip from an ACTIVE card directly to balance, transactions, or velocity investigation before checking the linked account and fraud-alert state.

Use `scripts/code05_plan.py` after normalizing the lookup results to obtain a deterministic next-step recommendation. It is a guardrail, not a bank-action executor.

## CODE 05 decision order

### 1. Card status

- **FROZEN:** Ask whether the customer wants to unfreeze it. If yes, require verified identity, card ownership, and an OPEN linked checking account. Unlock `unfreeze_debit_card_3893`, then call it with the card ID. Confirm that the card is active and immediately ready to use.
- **CLOSED:** Tell the customer the card is no longer active. Review cards on that account for another active or pending card and offer the applicable replacement/activation path; do not imply that a closed card can be reopened.
- **PENDING:** The card is not activated. Use the debit-card activation procedure rather than trying to clear the decline. Require verified identity, physical possession, card details, an OPEN account, a nonexpired PENDING card, and a compliant new PIN. Select the activation tool strictly from `issue_reason`: `activate_debit_card_8291` for `new_account`/`first_card`, `activate_debit_card_8292` for `lost`/`stolen`/`fraud`, or `activate_debit_card_8293` for `expired`/`damaged`/`upgrade`/`bank_reissue`.
- **ACTIVE:** Continue to step 2.
- **Missing, unknown, or inconsistent status:** do not take a card action. Re-run/clarify the card lookup; transfer for `technical_system_error` if a system data issue prevents completion.

### 2. Linked checking-account status

For an ACTIVE card, check the linked checking account returned by the account lookup.

- If its status is not OPEN, do not disclose whether it is suspended or restricted. Say exactly: **“Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”** Do not continue to clear alerts or blocks.
- If OPEN, continue to step 3.
- If the linked account cannot be determined or its status is unavailable, do not clear a protection; investigate the lookup problem first.

### 3. Fraud alert

Inspect `fraud_alert_active` and, if true, `alert_source`.

- **Customer-initiated:** Ask the customer to verify recent transactions. If they report unauthorized activity, cannot verify identity, or do not confirm the transactions are legitimate, do not clear the alert; transfer to security with `fraud_or_security_concern` where specialist handling is needed. Only after identity verification and confirmation that transactions are legitimate, unlock `clear_debit_card_fraud_alert_4892` and call it with `reason: "customer_verified"`. Document why it was cleared in interaction notes.
- **Bank-initiated:** Do not unlock or call the clear tool. Say: **“I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.”** Then call `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise summary.
- **No alert:** Continue to step 4.
- **Alert state/source unavailable:** do not assume no alert. Recheck the debit-card response or escalate a blocking system failure.

### 4. Velocity block

- If `velocity_blocked` is true, say: **“Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?”** Clear it early only after verified identity and a reasonable customer explanation. Unlock `clear_debit_card_fraud_alert_4892` and call it with `reason: "velocity_clear"`; document the reason.
- If false, tell the customer that the required CODE 05 card-status, account-status, fraud-alert, and velocity checks found no listed block. Collect the decline amount, time, merchant, and any relevant screenshots before further investigation or escalation. Do not invent a cause.

## Multiple declines and continuing the conversation

After resolving or safely pausing the selected card, repeat the same independent workflow for each additional card only if the customer wants to proceed. Product-level facts (for example, fees or limits) do not identify a physical card and must not substitute for card lookup.

For persistent unexplained errors, capture timestamps, screenshots, exact workflow, device/browser/app version, and repeated-attempt details. If a system error prevents investigation, use the highest applicable transfer reason, normally `technical_system_error`. If the customer reports fraud, identity concerns, or unauthorized transactions, use `fraud_or_security_concern`.

## Planning helper

Run the helper without executing any action:

```text
python3 scripts/code05_plan.py < request.json
```

It reads one JSON object from standard input and emits one JSON object to standard output. It accepts normalized lookup data:

- `card`: object with `card_id`, `account_id`, `user_id`, `status`, `fraud_alert_active`, `alert_source`, and `velocity_blocked` where available.
- `account`: linked account object with `account_id`, `account_type`, and `status` where available.
- `expected_user_id`: selected profile ID, optional but strongly recommended.
- `verified`: boolean indicating that the two-field verification and `log_verification` audit record are complete.
- `wants_unfreeze`, `recent_transactions_legitimate`, `wants_velocity_clear`, `velocity_explanation_acceptable`: booleans when the associated customer question has been answered.

The output contains `stage`, `next_step`, `required_before_action`, `recommended_tool`, `tool_arguments`, `customer_message`, and, when required, `transfer_reason`. Validate that an action recommendation has all listed prerequisites and that the tool arguments exactly match the selected card before using a banking tool.
