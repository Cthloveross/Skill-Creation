---
name: debit-card-code-05-investigation
description: Investigate one or more debit-card “CODE 05 / Do Not Honor” declines in the required order: card status, linked checking-account status, fraud alert, then velocity block. Use for verified banking customers with debit-card declines, including authorized unfreezing of a frozen card.
---

# Debit Card CODE 05 Investigation

## Safety and identity gate

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

A supplied name, email address, user ID, or profile lookup identifies a possible profile; it is not identity verification. Before disclosing account/card-specific findings or taking a card action:

1. Select the correct profile. If a name matches multiple profiles, request a distinguishing identifier such as email address or user ID.
2. Compare any two of date of birth, email, phone number, and address against the selected profile.
3. Retrieve the current time and call `log_verification` with the complete verified profile and timestamp only after two fields match.
4. Stop and transfer for security review if verification fails, is inconsistent, or raises impersonation concerns.

For every card action, confirm the verified customer owns the selected card and linked checking account and obtain explicit authorization for that action. Urgency or a merchant waiting does not bypass these controls.

## Runtime tool use

Use the execution agent's normal banking tools. For documented discoverable banking tools, unlock the tool first, then invoke it through `call_discoverable_agent_tool` with its arguments encoded as a JSON string. Do not invent IDs, fields, tools, or results.

Maintain a case record with the selected user ID, verification status, reported declines, checking accounts, cards, card-to-merchant mappings, and all action prerequisites and confirmations.

Use these documented lookups after the identity gate:

1. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with `{"user_id":"<selected user id>"}`.
2. Retain checking accounts and their actual statuses.
3. For each relevant checking account, unlock `get_debit_cards_by_account_id_7823`, then call it with `{"account_id":"<checking account id>"}`.

Do not substitute credit-card records for debit-card or checking-account records.

## End-to-end procedure

1. **Map each decline.** Ask the customer to associate each merchant decline with a card's last four digits. A stated account name alone can be ambiguous when multiple cards exist. If lookup data shows exactly one plausible card on an identified checking account, ask the customer to confirm that mapping. Keep each merchant/card investigation separate.
2. **Confirm card ownership and linkage.** The selected card must belong to the verified user and its `account_id` must match the checking account being assessed.
3. **Assess each selected card in order.** Supply actual lookup values to `scripts/code05_assessment.py`. The helper is read-only; tool responses and customer answers remain authoritative.
4. **Check card status first.**
   - `FROZEN`: ask whether the customer wants to unfreeze it. If they explicitly authorize unfreezing, follow the approved unfreeze procedure below.
   - `CLOSED`: explain that the card is no longer active. Check for another active card or an approved replacement workflow.
   - `PENDING`: explain that it is not activated and use an approved activation procedure if available.
   - `ACTIVE`: continue to the linked-account check.
   - Missing or unrecognized status: obtain complete card data; do not infer usability.
5. **Check linked checking-account status second for an active card.** If the account is not `OPEN`, do not disclose details of a `SUSPENDED` or `RESTRICTED` status. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Do not perform transaction-enabling actions on a non-open account.
6. **Check fraud alert third for an active card on an open account.**
   - If `fraud_alert_active` is false, continue to velocity.
   - If the alert is `customer_initiated`, have the verified customer review and confirm recent transactions are legitimate. Only then may the documented clearing workflow be used with reason `customer_verified`; document the reason.
   - If the alert is `bank_initiated`, do not clear it. Explain that additional security review is required and transfer to the security team.
   - If alert state or source is absent or contradictory, obtain complete data or escalate; never treat missing information as no alert.
7. **Check velocity block fourth.** If `velocity_blocked` is true, explain that the security system temporarily blocked the card because of unusual activity and that the block automatically lifts after 30 minutes. Early clearing requires logged identity verification, ownership confirmation, a reasonable explanation, explicit consent, and the documented clearing workflow with reason `velocity_clear`. Document the reason.
8. **Close out.** Confirm only actions whose tool result reports success. If all checks are clear but declines persist, collect the decline time, merchant/terminal, amount, screenshots or error text, device/app/browser version, and exact workflow. Escalate with logs when repeated attempts show the same error.

## Approved frozen-card unfreeze procedure

A frozen debit card has an approved unfreeze workflow. Never state or imply that such a workflow is unavailable merely because it has not yet been unlocked.

Before unfreezing, verify all of the following from current records and the conversation:

- identity verification was logged;
- the verified customer owns the selected card and linked checking account;
- the card's actual status is `FROZEN`;
- the linked checking account's actual status is `OPEN`; and
- the customer explicitly confirmed that they want this card unfrozen.

When all prerequisites are met:

1. Unlock `unfreeze_debit_card_3893`.
2. Call it through `call_discoverable_agent_tool` with `agent_tool_name` set to `unfreeze_debit_card_3893` and `arguments` set to the JSON string `{"card_id":"<selected frozen card id>"}`.
3. Inspect the result. Only if it reports success, tell the customer the card is active and ready to use immediately. If the tool returns an error or cannot complete, accurately explain the failure and use an appropriate human handoff when needed; do not claim the card was unfrozen.

This workflow does not authorize unfreezing a lost or stolen card. If the customer says the card is lost or stolen, follow the applicable replacement/security process instead.

## Human handoff

If a security escalation is required, a supported workflow fails, or the customer requests a human agent, use `transfer_to_human_agents` with the applicable available reason and a concise factual summary. If the customer accepts an offered transfer, dispatch the transfer in the runtime. Do not infer that a transfer did or did not occur solely from absence of a later public trace event, and do not claim dispatch succeeded unless the runtime result supports that statement.

## Assessment helper

`scripts/code05_assessment.py` is a deterministic, read-only planner. It does not call tools and does not authorize actions. It reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "card": {
    "card_id": "...",
    "account_id": "...",
    "status": "FROZEN",
    "fraud_alert_active": false,
    "velocity_blocked": false
  },
  "account": {"account_id": "...", "status": "OPEN"},
  "identity_verified": true,
  "owner_confirmed": true,
  "action_confirmed": true,
  "transactions_confirmed_legitimate": false,
  "reasonable_velocity_explanation": false
}
```

`card` and `account` are required lookup objects. Confirmation flags must be JSON booleans and default to `false` when absent. The helper emits `valid`, `stage`, `finding`, `customer_message`, `required_next`, and `permitted_action`; it emits `errors` for invalid inputs.

Run it with runtime-provided JSON:

```sh
printf '%s' "$INPUT_JSON" | python3 scripts/code05_assessment.py
```

Validate that `valid` is true, the returned stage is the next required stage, and every action prerequisite is independently supported by live lookup data and the conversation. `obtain_data`, `transfer_security`, and `none` never permit a clearance or unfreeze action.
