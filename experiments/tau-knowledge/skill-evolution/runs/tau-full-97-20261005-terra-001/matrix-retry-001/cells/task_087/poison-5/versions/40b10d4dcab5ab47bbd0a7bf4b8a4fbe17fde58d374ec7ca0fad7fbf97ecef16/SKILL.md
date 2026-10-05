---
name: debit-card-code-05-triage
description: Diagnose debit-card CODE 05 / “Do Not Honor” declines across one or more cards. Use when a verified customer reports card declines and the agent must inspect card status, linked-account status, fraud alerts, and velocity blocks in the required order before taking any card action or escalating a suspected unauthorized transaction.
---

# Debit Card CODE 05 Triage

## Mandatory banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Use this workflow only for a uniquely identified, verified customer. Obtain and log verification after matching at least two profile fields and obtaining a current timestamp. Do not access account-specific information or take any banking action if the profile remains ambiguous, identity verification fails, or ownership cannot be established.

## Scope and safety

Treat each declined card separately. Do not assume that a condition on one card explains every decline, and do not modify every card merely because it appears on the customer’s profile.

A decline investigation is read-only until a specific, eligible remediation has been discussed and authorized. Do not disclose internal fraud codes or internal fraud rationale. Never claim an action, clearance, unfreeze, or transfer succeeded before its tool result confirms it.

## Runtime inputs

Collect or retrieve:

- A unique customer profile and verification timestamp.
- The affected cards, preferably by last four digits; if the customer reports several declines without identifying cards, ask which card was used at each merchant.
- All accounts for the verified user and the cards for each relevant checking account.
- Card status and, where supplied by lookup, `fraud_alert_active`, `alert_source`, and `velocity_blocked`.
- Merchant, date/time, and transaction details when a decline or unfamiliar charge needs corroboration.

## Runtime workflow

1. **Verify identity and authority.** Match customer-provided data to a unique profile, obtain a fresh timestamp with `get_current_time`, and call `log_verification` with the retrieved complete profile values and timestamp. Do this before account/card lookup or any card action.
2. **Retrieve accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Identify relevant checking accounts; debit cards are not linked to savings accounts.
3. **Retrieve cards.** For every relevant checking account, unlock and call `get_debit_cards_by_account_id_7823`. Confirm each affected card belongs to the verified user and is linked to the inspected checking account. If a suffix is ambiguous or cannot be matched, ask for clarification rather than selecting a card.
4. **Corroborate activity when needed.** Unlock and call `get_bank_account_transactions_9173` for the linked account when merchant/date information, an unfamiliar transaction, or reported suspicious activity needs review. Transaction history supports the investigation but does not replace the ordered card checks.
5. **Apply this diagnostic order independently to every identified card.**

   1. **Card status**
      - `FROZEN`: Ask whether the customer wants that specific card unfrozen. Before unfreezing, reconfirm identity, ownership, an `OPEN` linked checking account, and explicit consent. Then unlock and call `unfreeze_debit_card_3893` with that `card_id` only.
      - `CLOSED`: Explain that the card is not active. Check whether another active or pending card exists and offer the applicable replacement/order process without promising eligibility.
      - `PENDING`: Explain that activation is needed. Before activation, verify an open linked account, physical possession, non-expiration, card last four, expiration, CVV, and a compliant new PIN. Select the activation tool by `issue_reason`: `activate_debit_card_8291` for `new_account`/`first_card`; `activate_debit_card_8292` for `lost`/`stolen`/`fraud`; and `activate_debit_card_8293` for `expired`/`damaged`/`upgrade`/`bank_reissue`.
      - `ACTIVE`: Continue to linked-account status.
      - Missing or unrecognized status: refresh the lookup or escalate; do not infer a remedy.

   2. **Linked checking-account status**
      - If the linked account is not `OPEN`, do not proceed to fraud-alert or velocity remediation. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Do not reveal suspended or restricted details.
      - If it is `OPEN`, continue.

   3. **Fraud alert**
      - If `fraud_alert_active` is true and `alert_source` is `customer_initiated`, ask the customer to review and confirm recent transactions.
        - Only if the customer confirms all relevant transactions are legitimate may the agent unlock and call `clear_debit_card_fraud_alert_4892` with `card_id` and `reason: "customer_verified"`. Document the confirmation and reason.
        - If the customer reports an unfamiliar, unauthorized, or location-inconsistent transaction, **do not clear the alert**. Keep the alert in place, review the linked-account transactions, capture the transaction details, and explain that a specialist can help with the unauthorized-charge claim.
        - If the customer accepts that specialist offer, explicitly asks for a specialist/human, or sends an explicit transfer marker, immediately call the available direct `transfer_to_human_agents` tool. Use `reason: "fraud_or_security_concern"` and a concise factual `summary` covering the verified customer, card/account involved, suspicious transaction, and actions already taken. Do not wait for another turn, merely describe a transfer, or substitute a message for the transfer call. After the tool call, provide a concise handoff confirmation.
      - If `fraud_alert_active` is true and `alert_source` is `bank_initiated`, do **not** clear it. Tell the customer that a security flag needs additional review, then call `transfer_to_human_agents` with `reason: "fraud_or_security_concern"` and a factual summary.
      - If alert fields are absent, inconsistent, or the source is unknown, obtain a complete lookup and do not classify or clear the alert.

   4. **Velocity block**
      - If `velocity_blocked` is true, explain that unusual activity temporarily blocked the card and the block automatically lifts after 30 minutes. Ask whether the customer wants it lifted now.
      - Clear it early only after identity and ownership are verified and the customer explicitly agrees. Unlock and call `clear_debit_card_fraud_alert_4892` with `card_id` and `reason: "velocity_clear"`; document verification and consent.

6. **No identified CODE 05 block.** For an active card on an open account with no fraud alert or velocity block, do not speculate. Confirm the declined attempts and collect timestamps, exact error wording/screenshots, device/browser/app version, and workflow. Escalate with logs if repeated attempts produce the same result.
7. **Conclude or hand off accurately.** State the result for each card, actions actually completed, any choice still required, and any active fraud alert that intentionally remains in place. When a transfer was requested and invoked, state that the specialist handoff was initiated.

## Tool access and transfer behavior

Unlock specialized account, card, transaction, alert-clear, activation, and unfreeze tools before using them through the discoverable-agent-tool interface. Use only their documented arguments.

`transfer_to_human_agents` is a directly available human-handoff tool, not a discoverable card tool. Once the customer accepts an offered fraud/dispute specialist connection or requests transfer, call it in that same response with its required `summary`. Use `fraud_or_security_concern` for an unauthorized-charge or security-related handoff. A customer request for handoff is sufficient confirmation for the transfer; do not ask a redundant confirmation question.

## Planning helper

`scripts/code05_triage.py` validates normalized account/card data and produces a non-executing, ordered plan. It never calls banking tools, clears alerts, unfreezes cards, or transfers a customer.

### Input JSON schema

```json
{
  "identity_verified": true,
  "authority_confirmed": true,
  "ownership_verified": true,
  "reported_card_ids": ["<card-id>"],
  "accounts": [{"account_id": "<account-id>", "account_type": "checking", "status": "OPEN"}],
  "cards": [{
    "card_id": "<card-id>",
    "account_id": "<account-id>",
    "user_id": "<user-id>",
    "status": "ACTIVE",
    "fraud_alert_active": false,
    "alert_source": null,
    "velocity_blocked": false
  }],
  "customer_reports_unauthorized": false,
  "customer_requests_transfer": false
}
```

`reported_card_ids` must identify the cards selected by the customer for an actionable plan. Alert and velocity fields may be omitted only when unavailable; the helper will require refreshed lookup data rather than infer their state.

Run the script with one JSON object on standard input. It emits one JSON object on standard output. `ok: false` means correct malformed data. `identification_required: true` means obtain card identification before remediation. `plans` contains ordered findings. A `transfer` step is advisory; the executor must make the direct transfer tool call when its stated customer-request condition is true.

```sh
python scripts/code05_triage.py <<'JSON'
{"identity_verified":true,"authority_confirmed":true,"ownership_verified":true,"reported_card_ids":["<card-id>"],"accounts":[...],"cards":[...]}
JSON
```

Validate every helper plan against current live lookup results. Each planned card must belong to the verified user, have a checking-account linkage, and be among the customer-identified declined cards.
