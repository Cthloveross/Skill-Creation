---
name: investigate-debit-card-code-05
version: 1.0.0
description: Investigate one or more Rho-Bank debit-card CODE 05 (Do Not Honor) declines in the required order: card status, linked checking-account status, fraud alert, then velocity block. Use when a verified customer reports debit-card declines and the agent has access to the debit-card and account lookup tools.
---

# Investigate Debit-Card CODE 05 Declines

Use this Skill for debit cards only. Do not substitute credit-card searches for debit-card investigation. A CODE 05 is a generic decline and must be evaluated in this order for every affected card:

1. card status;
2. linked checking-account status;
3. fraud alert;
4. velocity block.

The included helper is advisory only: it never contacts bank systems, changes a card, clears a security control, or transfers a customer.

## Inputs and prerequisites

Collect enough information to locate the customer and identify the affected Rho-Bank debit cards. If the customer cannot provide last four digits, enumerate the debit cards on each of their checking accounts and carefully describe only the minimum non-sensitive identifying information needed to establish which cards are affected.

Before any state-changing action (unfreeze, clear alert/block, or activate), verify identity and card ownership:

1. Ask the customer to state at least two of date of birth, email, phone number, and address. Do not count facts merely retrieved from the bank system as customer confirmation.
2. Retrieve the customer record and compare the stated values to it.
3. Get the current timestamp with `get_current_time` and call `log_verification` with the complete retrieved identity record and that timestamp.

A prior verified identity record can be used only if the current interaction and policy permit it. If identity cannot be verified, do not clear any alert or block and do not activate or unfreeze a card.

## Runtime tool procedure

### 1. Locate the customer and accounts

* Use `get_user_information_by_email`, `get_user_information_by_id`, or `get_user_information_by_name` to find the customer. Resolve duplicate names using a customer-provided identifier.
* Unlock `get_all_user_accounts_by_user_id_3847`, then call it through `call_discoverable_agent_tool` with `{"user_id":"..."}`.
* Retain every checking account's `account_id` and `status`. Debit cards are linked only to checking accounts.
* Unlock `get_debit_cards_by_account_id_7823`, then call it for every relevant checking `account_id` using `{"account_id":"..."}`.

Use the returned `card_id`, `account_id`, last four digits, status, issue reason, and security fields to associate each reported decline with a card. If a card cannot be identified or lookup data is incomplete, explain that the investigation cannot be completed from available records; use `technical_system_error` only when an actual system/tool failure prevents completion, otherwise gather the missing information.

Transaction history can help review the reported restaurant, fuel, or grocery attempts but does not replace the required CODE 05 order. When needed, unlock `get_bank_account_transactions_9173` and call it with the relevant account ID. Review only relevant debit-card purchases and their pending/posted status.

### 2. Apply the CODE 05 decision order per card

For each affected card, use the helper or follow this table. Do not skip ahead to fraud or velocity when an earlier step resolves or blocks the case.

| Check | Result | Required response / next step |
|---|---|---|
| Card status | `FROZEN` | Ask whether the customer wants to unfreeze it. Unfreezing requires verified ownership and an OPEN linked checking account. If they consent and prerequisites hold, unlock `unfreeze_debit_card_3893`, call it with `{"card_id":"..."}`, and confirm it is active. |
| Card status | `CLOSED` | Explain that it is no longer active. Check for another active card or offer a replacement according to available card-order procedures. |
| Card status | `PENDING` | It has not been activated. Follow the activation protocol; do not attempt a CODE 05 security-control action first. |
| Card status | `ACTIVE` | Continue to linked account status. |
| Linked checking account | anything other than `OPEN` | Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Do not disclose details for suspended or restricted accounts. |
| Fraud alert | active, `alert_source = bank_initiated` | Do not clear it. Tell the customer: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Transfer with reason `fraud_or_security_concern` and a concise factual summary. |
| Fraud alert | active, `alert_source = customer_initiated` | Ask the customer to verify recent transactions. Clear only after verified identity **and** their affirmative confirmation that the transactions are legitimate. Unlock `clear_debit_card_fraud_alert_4892`, then call it with `{"card_id":"...","reason":"customer_verified"}`. Never use it for a bank-initiated alert. |
| Velocity block | `true` | Explain it is a temporary unusual-activity block that automatically lifts after 30 minutes. Offer an early lift only after identity verification and a reasonable explanation. If the customer wants it cleared and prerequisites hold, unlock `clear_debit_card_fraud_alert_4892` and call it with `{"card_id":"...","reason":"velocity_clear"}`. |

Treat an unknown or absent security field as unknown, not false. Request/obtain the missing authoritative lookup data rather than clearing a control based on assumption.

### 3. Activation branch

For a pending card, require verified identity, customer possession of the physical card, OPEN linked checking account, unexpired card, matching last four digits/expiration/CVV, and a valid non-sequential, non-repeating four-digit PIN. Select the activation tool only from `issue_reason`:

* `new_account` or `first_card` → unlock and use `activate_debit_card_8291`.
* `lost`, `stolen`, or `fraud` → unlock and use `activate_debit_card_8292`.
* `expired`, `damaged`, `upgrade`, or `bank_reissue` → unlock and use `activate_debit_card_8293`.

Do not guess the activation tool or activate a card after two incorrect detail attempts.

### 4. Completion and escalation

Report the outcome separately for each card without exposing full card numbers or restricted-account details. Confirm any successful change using the tool response. For a bank-initiated fraud alert, suspected unauthorized activity, failed identity verification, or suspicious/inconsistent explanation, do not make a security change; transfer to the security team with `fraud_or_security_concern`.

## Advisory helper

`scripts/code05_plan.py` accepts JSON on stdin and emits JSON on stdout. It produces an ordered advisory plan for one card and does not invoke banking tools.

Input schema:

```json
{
  "card": {
    "card_id": "string",
    "account_id": "string",
    "status": "ACTIVE|FROZEN|CLOSED|PENDING",
    "fraud_alert_active": true,
    "alert_source": "customer_initiated|bank_initiated|null",
    "velocity_blocked": false
  },
  "account_status": "OPEN",
  "identity_verified": false,
  "customer_confirms_transactions_legitimate": false,
  "customer_wants_unfreeze": false,
  "customer_requests_early_velocity_clear": false,
  "reasonable_velocity_explanation": false
}
```

All Boolean values must be actual JSON booleans. Omit optional consent/confirmation fields only when the customer has not answered; the helper treats omission as `false`. `account_status` and the card status are required. A malformed input returns `{"ok": false, "error": "..."}`. Successful output has `ok: true`, an ordered `outcome`, and advisory `steps`. An action marked `agent_action_required` must still be performed only with the declared banking tools after checking live prerequisites.

Example executable call in the isolated Skill runtime:

```text
run_skill_script(relative_path="scripts/code05_plan.py", input_json={"card":{"card_id":"<card id>","account_id":"<checking id>","status":"ACTIVE","fraud_alert_active":false,"alert_source":null,"velocity_blocked":true},"account_status":"OPEN","identity_verified":true,"customer_requests_early_velocity_clear":true,"reasonable_velocity_explanation":true})
```

Validate the helper result before relying on it: ensure `ok` is true, its first substantive step is consistent with card status, and no `clear_*` action is used unless the output explicitly lists the required verification/consent conditions. The live tool responses, not this helper, are authoritative.
