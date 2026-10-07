---
name: debit-card-code-05-triage
description: Investigate debit-card “CODE 05 / Do Not Honor” declines for an identified customer. Use for one or multiple debit-card declines when the agent must check card status, linked checking-account status, fraud alerts, and velocity blocks in order, while taking only authorized card actions.
---

# Debit Card CODE 05 Triage

## Scope and security rules

Treat each reported decline as card-specific. Work on the card/account the customer selects first, then repeat the complete workflow independently for each other affected card if the customer wants to continue.

A profile lookup or a customer-provided email identifies a record but is **not** sufficient verification for a state-changing action. Before unfreezing a card or clearing a security protection:

1. Ask the customer to provide (do not read back) at least two of date of birth, email, phone number, and address.
2. Compare the provided values to the selected profile.
3. Obtain the current time with `get_current_time`.
4. Call `log_verification` with the complete profile fields and the timestamp.

Use normal banking tools only after all stated prerequisites are met. Do not clear a bank-initiated fraud alert. Do not disclose internal fraud codes or internal detection details.

## Runtime inputs

- A uniquely identified customer profile and `user_id`.
- The selected affected card or checking account. Last four digits are preferred. A product/account description may be used only when it uniquely identifies a returned checking account.
- Customer verification state, card ownership, and any required consent or transaction confirmation.

If an account description is ambiguous, request the card last four digits or clarify the checking account. Do not infer a physical card from unrelated profile, balance, fee, or product information.

## Lookup and validation sequence

1. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847(user_id)` (unlock it, then call through `call_discoverable_agent_tool`).
2. Locate the selected **checking** account and record its status.
3. Retrieve cards for that exact account with `get_debit_cards_by_account_id_7823(account_id)` (unlock it, then call through `call_discoverable_agent_tool`).
4. Match the reported card, retain its `card_id`, `account_id`, `user_id`, status, fraud-alert fields, and velocity field, and confirm that it belongs to both the selected account and identified customer.
5. A card/profile ownership mismatch is a security issue. Take no card action; transfer with `account_ownership_dispute` and a factual summary.
6. Follow the CODE 05 decision order below. A status-changing action such as unfreezing corrects only card status; it does **not** end the required account, fraud-alert, and velocity review.

The optional `scripts/code05_plan.py` helper converts normalized results into a next-step recommendation. It never calls banking tools and is only a guardrail.

## CODE 05 decision order

### 1. Card status

- **FROZEN:** Ask whether the customer wants it unfrozen. If yes, require verified identity, confirmed ownership, and an OPEN linked checking account. Unlock and call `unfreeze_debit_card_3893` with the card ID. Confirm successful unfreezing, but do **not** promise that all transactions will now process: immediately continue the account, fraud-alert, and velocity checks below using the lookup data (or a refreshed card lookup if needed).
- **CLOSED:** Tell the customer the card is no longer active. Review cards on that account for another active or pending card and offer the applicable replacement or activation path. Never imply a closed card can be reopened.
- **PENDING:** Follow the activation procedure, not an alert-clear procedure. Require verified identity, physical possession, OPEN account, nonexpired PENDING card, card details, and a compliant new PIN. Select the activation tool from `issue_reason`: `activate_debit_card_8291` for `new_account`/`first_card`; `activate_debit_card_8292` for `lost`/`stolen`/`fraud`; and `activate_debit_card_8293` for `expired`/`damaged`/`upgrade`/`bank_reissue`.
- **ACTIVE:** Continue to account status.
- **Missing, unknown, or inconsistent status:** take no card action. Recheck the lookup and transfer for `technical_system_error` if the data problem prevents completion.

### 2. Linked checking-account status

Check the selected card's linked checking account, including before an unfreeze.

- If the account is not OPEN, do not reveal whether it is suspended or restricted. Say exactly: **“Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”** Do not unfreeze the card or clear alerts/blocks.
- If the account is OPEN, continue to fraud alert.
- If the linked account or its status cannot be established, do not clear a protection. Resolve the lookup problem first.

### 3. Fraud alert

Inspect `fraud_alert_active` and, when true, `alert_source`.

- **Customer-initiated alert:** Ask the customer to verify recent transactions. If they report an unauthorized or suspicious transaction, cannot verify identity, or cannot confirm the transactions are legitimate, leave the alert in place and transfer with `fraud_or_security_concern`. Only after verified identity and confirmation that transactions are legitimate may the agent call the normal `clear_debit_card_fraud_alert_4892` tool with `card_id` and `reason: "customer_verified"`. Document why the alert was cleared in interaction notes.
- **Bank-initiated alert:** Do not call the clear tool. Say: **“I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.”** Then transfer using `fraud_or_security_concern` with a concise summary.
- **No alert:** Continue to velocity.
- **Unavailable alert state/source:** do not assume that no alert exists. Recheck the card response or escalate a blocking system issue.

### 4. Velocity block

Always evaluate this step after the fraud-alert step, including after a card was successfully unfrozen. A frozen-card resolution alone does not resolve `velocity_blocked: true`.

- If `velocity_blocked` is true, tell the customer: **“Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?”** This disclosure and offer must be made promptly after an unfreeze when the lookup showed a velocity block. Do not state that the card is fully ready for normal transactions while this block remains.
- For an early lift, obtain customer consent, verified identity, and a reasonable explanation for the unusual activity. Then call the normal `clear_debit_card_fraud_alert_4892` tool with the selected `card_id` and `reason: "velocity_clear"`; document the explanation and reason in interaction notes.
- If the customer declines an early lift, explain that the temporary block automatically expires after 30 minutes.
- If `velocity_blocked` is false, explain only that the required card, account, fraud-alert, and velocity checks found no listed block. Collect the decline amount, time, merchant, screenshots, device/browser/app version, and repeated-attempt details before further investigation. Do not invent a cause.

## Continuing multiple-card investigations

After resolving or safely pausing one card, perform the same independent account lookup, card lookup, ownership check, and ordered CODE 05 review for each remaining reported card. Do not apply the state of one card to another card.

For persistent unexplained errors, retain timestamps, screenshots, exact workflow, device/browser/app version, and repeated-attempt details. Use `technical_system_error` when a system issue prevents completion. Use `fraud_or_security_concern` when the customer reports unauthorized activity, fraud, or an identity concern.

## Planning helper

Run the helper without executing actions:

```text
python3 scripts/code05_plan.py < request.json
```

It reads one JSON object from stdin and emits one JSON object to stdout. Input fields are:

- `card`: normalized card object. Expected fields when available are `card_id`, `account_id`, `user_id`, `status`, `fraud_alert_active`, `alert_source`, and `velocity_blocked`.
- `account`: normalized linked account object with `account_id`, `account_type`, and `status`.
- `expected_user_id`: selected customer ID.
- `verified`: true only after two-field verification and a successful `log_verification` audit record.
- `wants_unfreeze`, `recent_transactions_legitimate`, `wants_velocity_clear`, and `velocity_explanation_acceptable`: customer responses for their corresponding questions.
- `unfreeze_completed`: true only after `unfreeze_debit_card_3893` succeeded for this exact selected card. Supplying this resumes the required fraud and velocity review even if the original lookup still says `FROZEN`.

Output fields include `stage`, `next_step`, `required_before_action`, `recommended_tool`, `tool_arguments`, `customer_message`, and `transfer_reason` where applicable. Validate every prerequisite and ensure recommended tool arguments still match the selected card before using any banking tool.
