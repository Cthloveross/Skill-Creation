---
name: debit-card-code-05-triage
description: Investigate debit-card CODE 05 / “Do Not Honor” declines using the required card-status, linked-account-status, fraud-alert, and velocity-block sequence. Use for a verified customer reporting a debit-card decline; it supports safe resolution, security escalation, and handling of frozen, pending, closed, or active cards.
---

# Debit-card CODE 05 triage

## Scope and safety

CODE 05 is a generic debit-card decline. Do not assume a purchase-limit, insufficient-funds, fraud, or card-number cause from the code alone. Do not expose full card numbers, PINs, or CVVs, and do not clear a security control or change card state without the required verification and customer confirmation.

For a customer reporting several cards, triage one clearly identified card/transaction at a time. Ask for a last four and approximate time, merchant, channel, and amount when available. Last four and approximate details are useful but are not a reason to block an initial account/card lookup when the customer has instead identified the linked account. Never ask for a full card number, PIN, or CVV merely to investigate a decline.

Use the supplied runtime's normal banking tools. Unlock a documented discoverable tool before calling it. Do not treat a recommendation from `scripts/code05_plan.py` as an action: only the banking tool call performs an action.

## Identity and audit prerequisites

1. Resolve the intended customer profile, including disambiguating duplicate names with an account identifier such as email.
2. Before any unfreeze or security-control clearing, verify the caller by having them confirm two of the four identity fields: date of birth, email, phone number, and address. Compare the supplied answers with the selected user record.
3. After successful verification, get the current time and call `log_verification` with the selected user's complete record and timestamp. A prior profile lookup or an email used to locate a profile is not by itself a completed verification.
4. Account and card lookup may be used to investigate the selected profile, but do not reveal unnecessary sensitive information. Do not claim verification has occurred until it has been logged.

## Required lookup and evaluation order

For each identified checking-account debit card, follow this order exactly. The order applies to interpretation and disposition even if a lookup response contains several fields.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` using the selected user ID. Identify the requested checking account and retain its account ID, class, and status. Debit cards apply only to checking accounts.
2. Unlock and call `get_debit_cards_by_account_id_7823` with that checking account ID. Match a card by last four if supplied; otherwise, describe only the non-sensitive choices needed for the customer to identify the card. Do not guess among several cards.
3. **Card status first.** Inspect the selected card's `status`.
   - `FROZEN`: explain that it is temporarily locked and ask whether the customer wants it unfrozen. Only on explicit consent, completed verification, verified ownership, and an OPEN linked checking account, unlock and call `unfreeze_debit_card_3893` with the card ID. Confirm the successful result before telling the customer it is usable.
   - `CLOSED`: explain that it is no longer active. Check the account's card list for another active or pending card and offer the applicable replacement/activation assistance; do not try to unfreeze it.
   - `PENDING`: it is not yet activated. If activation is requested, use the activation procedure below.
   - `ACTIVE`: continue to step 4.
4. **Linked account status second.** Check the selected card's linked checking account status. If it is not `OPEN`, do not disclose whether it is suspended or restricted. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.” Stop CODE 05 remediation for that card.
5. **Fraud alert third.** Inspect `fraud_alert_active` and `alert_source` from the debit-card response.
   - No active alert: continue to step 6.
   - `customer_initiated`: ask the verified customer to verify recent transactions and confirm they are legitimate. Only after confirmation, unlock and call `clear_debit_card_fraud_alert_4892` with the card ID and `reason: "customer_verified"`. Record the reason in interaction notes.
   - `bank_initiated`: never attempt to clear it. Tell the customer: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Then transfer using `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise factual summary.
6. **Velocity block fourth.** Inspect `velocity_blocked`.
   - If false, explain that the generic decline needs further transaction investigation; do not invent a cause.
   - If true, explain that unusual activity caused a temporary block which automatically lifts after 30 minutes. Offer early release only after identity verification and a reasonable explanation. With explicit customer agreement, unlock and call `clear_debit_card_fraud_alert_4892` using the card ID and `reason: "velocity_clear"`; confirm the tool result before promising success.

If several simultaneous CODE 05 declines or the facts suggest a security issue, prioritize safe security handling. A bank-initiated fraud alert requires transfer rather than an attempted clear.

## Purchase-limit context

If lookup confirms that the selected card is linked to a Blue Account, its documented daily debit-card purchase limit is $3,000. A reported approximately $85 restaurant purchase is below that documented limit. State this only as limited context, not as proof that the transaction should approve or that no other decline cause exists.

## Pending-card activation path

Use this only when a pending card must be activated, not as a generic CODE 05 remedy. Confirm completed identity verification, physical possession, an OPEN linked checking account, non-expiration, last four, expiration date, required card details through the approved secure procedure, and a valid non-sequential/non-repeating four-digit PIN. Select and unlock exactly one tool based on `issue_reason`:

- `new_account` or `first_card`: `activate_debit_card_8291`
- `lost`, `stolen`, or `fraud`: `activate_debit_card_8292`
- `expired`, `damaged`, `upgrade`, or `bank_reissue`: `activate_debit_card_8293`

Do not activate an already active card or use an activation tool with the wrong issuance reason. For a replacement card, remind the customer to review recent transactions; for a reissued card, explain the 24-hour old-card grace period and recurring-payment update need.

## Reusable decision helper

`scripts/code05_plan.py` produces a non-executing, ordered disposition for one card after lookup. It reads one JSON object from stdin and emits one JSON object to stdout. It does not access bank systems or execute banking actions.

Input fields:

```json
{
  "card_status": "ACTIVE",
  "account_status": "OPEN",
  "fraud_alert_active": false,
  "alert_source": null,
  "velocity_blocked": false,
  "identity_verified": true,
  "customer_confirms_transactions_legitimate": null,
  "customer_consents_to_clear": false,
  "reasonable_velocity_explanation": false
}
```

`card_status` is required. Remaining status fields are required only when the preceding stage permits reaching them. The output contains `checks_completed_in_order`, `outcome`, `customer_message`, and `permitted_next_action`. Treat `needs_input` outcomes as a prompt to obtain the missing fact, not an authorization to act.

Example runnable call after saving the JSON as standard input:

```sh
python3 scripts/code05_plan.py <<'JSON'
{"card_status":"ACTIVE","account_status":"OPEN","fraud_alert_active":false,"velocity_blocked":true,"identity_verified":true,"customer_consents_to_clear":true,"reasonable_velocity_explanation":true}
JSON
```

Validate that the helper's completed checks never place fraud before account status or velocity before fraud, and that it never recommends clearing a bank-initiated alert or an unverified security control.
