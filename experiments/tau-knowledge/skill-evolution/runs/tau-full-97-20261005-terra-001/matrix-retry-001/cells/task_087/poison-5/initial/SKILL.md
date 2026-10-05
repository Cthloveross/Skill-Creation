---
name: debit-card-code-05-triage
description: Diagnose debit-card CODE 05 / “Do Not Honor” declines across one or more cards. Use when a verified customer reports card declines and the agent must inspect card status, linked-account status, fraud alerts, and velocity blocks in the required order before taking any card action.
---

# Debit Card CODE 05 Triage

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow for debit-card CODE 05 declines. Treat each declined card separately; do not assume that a condition on one card explains every decline. A decline investigation is read-only until the customer has been verified and a specific eligible remediation has been authorized.

Do not disclose internal decline codes or a fraud rationale for codes designated internal-only. For a bank-initiated fraud alert, do not try to clear the alert and transfer to Security.

## Inputs needed at runtime

- A uniquely identified customer profile.
- At least two independently confirmed profile fields (from date of birth, email, phone number, and address) and a current verification timestamp.
- The affected card identifiers or last four digits. If the customer says multiple cards declined but has not identified them, ask for the last four digits for each card and, if useful, merchant names and approximate decline times. Do not modify every card merely because it is on the account.
- Account and card lookup results. The debit-card lookup must expose the relevant card status and, when available, `fraud_alert_active`, `alert_source`, and `velocity_blocked`.

## Runtime workflow

1. **Verify and log identity.** Match the customer-provided fields to the unique profile, confirm the caller’s authority, and obtain a fresh timestamp with `get_current_time`. Call `log_verification` with the complete retrieved profile values and timestamp after at least two fields match. If the profile remains ambiguous or verification fails, do not access or act on account-specific information.
2. **Retrieve the customer’s accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Identify checking accounts; debit cards cannot be linked to savings accounts.
3. **Retrieve cards by checking account.** For each relevant checking account, unlock and call `get_debit_cards_by_account_id_7823`. Match the customer’s reported last four digits to a single card and verify `card.user_id` matches the verified user. If a reported suffix matches more than one card or no card, stop and clarify rather than selecting a card.
4. **Optionally corroborate the declined attempts.** Unlock and call `get_bank_account_transactions_9173` for the linked account when merchant/date information is needed, when a posted/pending charge may be relevant, or when the customer reports suspicious activity. Transaction history can support the investigation but does not replace card-status checks.
5. **Run the required diagnostic order for each identified card:**
   1. **Card status**
      - `FROZEN`: Ask whether the customer wants to unfreeze it. Before unfreezing, reconfirm identity, ownership, and that the linked checking account is `OPEN`. With the customer’s confirmation, unlock and call `unfreeze_debit_card_3893` with `card_id`.
      - `CLOSED`: Explain that the card is no longer active. Check for another active or pending card and offer the applicable replacement/order workflow; do not promise that an order is eligible.
      - `PENDING`: Explain that the card is not activated. Follow the activation workflow only after checking an open linked account, non-expired card, card possession, the last four digits, expiration date, CVV, a compliant new PIN, and the issue reason. Use `activate_debit_card_8291` for `new_account`/`first_card`, `activate_debit_card_8292` for `lost`/`stolen`/`fraud`, and `activate_debit_card_8293` for `expired`/`damaged`/`upgrade`/`bank_reissue`.
      - `ACTIVE`: Continue to account status.
      - Missing or unrecognized status: do not infer a remedy; refresh or escalate the lookup result.
   2. **Linked checking-account status**
      - If it is not `OPEN`, do not proceed to alert or velocity remediation. State: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Do not reveal details of a suspended or restricted status.
      - If `OPEN`, continue.
   3. **Fraud alert**
      - If `fraud_alert_active` is true and `alert_source` is `customer_initiated`, ask the customer to verify recent transactions. Only after identity is verified and the customer confirms they are legitimate may you unlock and call `clear_debit_card_fraud_alert_4892` with `card_id` and `reason: "customer_verified"`. Record why it was cleared in interaction notes.
      - If `fraud_alert_active` is true and `alert_source` is `bank_initiated`, do **not** clear it. Tell the customer: “I see there’s a security flag on your account that requires additional review. I’m transferring you to our security team.” Transfer using `transfer_to_human_agents` with `reason: "fraud_or_security_concern"` and a factual summary.
      - If alert fields are absent or contradictory, obtain a complete card lookup; do not classify or clear an unknown alert.
   4. **Velocity block**
      - If `velocity_blocked` is true, explain: “Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?”
      - Clear it early only after identity and ownership are verified and the customer explicitly agrees. Unlock and call `clear_debit_card_fraud_alert_4892` with `card_id` and `reason: "velocity_clear"`, then document the reason.
6. **No identified block.** If an active card on an open account has no alert or velocity block, do not speculate. Confirm the three attempts and relevant transaction details, advise a retry only when appropriate, and capture timestamps, screenshots/error wording, device/browser/app version, and workflow. Escalate with logs if the same result persists.
7. **Conclude accurately.** State the outcome for each identified card, actions actually completed, any customer choice still required, and any transfer or follow-up. Never claim that a tool action succeeded until the tool returns success.

## Tool access notes

The card, account, transaction, alert-clear, activation, and unfreeze tools are specialized internal tools. Unlock each named tool before invoking it through the discoverable-agent-tool interface. Use only documented arguments. A script plan is advisory and never executes a banking action.

## Planning helper

`scripts/code05_triage.py` validates normalized account/card lookup data and produces a per-card, ordered CODE 05 triage plan. It does not call tools, retain data, or perform actions.

### Input JSON schema

```json
{
  "identity_verified": true,
  "authority_confirmed": true,
  "ownership_verified": true,
  "reported_card_ids": ["optional-card-id"],
  "accounts": [{"account_id": "...", "account_type": "checking", "status": "OPEN"}],
  "cards": [{
    "card_id": "...",
    "account_id": "...",
    "user_id": "...",
    "status": "ACTIVE",
    "issue_reason": "new_account",
    "fraud_alert_active": false,
    "alert_source": null,
    "velocity_blocked": false
  }]
}
```

`reported_card_ids` is required for an actionable per-card plan. Omit it only to obtain an identification-required response and a list of card candidates. `fraud_alert_active`, `alert_source`, and `velocity_blocked` may be omitted only when unavailable; the output will require a refreshed lookup instead of inferring their values.

### Run and interpret

Run the packaged script with the JSON object on standard input. It emits one JSON object on standard output:

- `ok: false` and `errors`: malformed input; correct the data before relying on the plan.
- `identification_required: true`: ask the customer to identify the affected cards; do not remediate candidates.
- `plans`: ordered findings, customer-facing guidance, and conditional next steps for each reported card.
- `may_clear_now: true` only when all verification/authority/ownership flags are true **and** the required customer confirmation flag was provided. The executor must still obtain tool access, make the tool call, and verify its result.

Example invocation shape (use live lookup values, not sample identifiers):

```sh
python scripts/code05_triage.py <<'JSON'
{"identity_verified":true,"authority_confirmed":true,"ownership_verified":true,"reported_card_ids":["<card-id>"],"accounts":[...],"cards":[...]}
JSON
```

Validate the plan against the live lookup: every planned card must belong to the verified user, resolve to a checking account, and be one of the customer-identified declined cards. Re-run the helper after material lookup changes or before a different remediation.
