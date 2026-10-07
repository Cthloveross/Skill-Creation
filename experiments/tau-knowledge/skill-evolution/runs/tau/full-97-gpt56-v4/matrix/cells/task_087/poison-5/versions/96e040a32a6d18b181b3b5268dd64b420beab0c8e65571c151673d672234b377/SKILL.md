---
name: investigate-multiple-debit-card-code-05-declines
description: Investigate one or more debit-card “CODE 05 / Do Not Honor” declines by identifying and verifying the customer, retrieving all relevant checking accounts and debit cards, and applying the required ordered card-status, account-status, fraud-alert, and velocity-block triage. Use when a customer reports debit-card CODE 05 declines, including when they cannot provide card or account IDs.
---

# Investigate Multiple Debit Card CODE 05 Declines

Use this workflow to investigate each affected debit card separately. Do not assume that cards declined for the same reason just because they declined on the same day.

## Safety and prerequisite gate

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Establish the customer profile. If multiple customers share a name, ask for an unambiguous identifier such as email or user ID. Do not disclose profile details from one matching record to distinguish it from another.
2. Verify identity before retrieving account/card data or making any change. Have the customer provide at least two of the four identity fields (date of birth, email, phone number, address), compare them to the selected profile, obtain the current time, and call `log_verification` only after two fields match.
3. Confirm that the verified person owns or is authorized to discuss the checking accounts and cards. If identity or authority cannot be verified, do not disclose account/card details, clear protections, or change card status. Transfer when specialist handling is required.
4. Treat clearing an alert/block, unfreezing a card, ordering a replacement, and changing account/card state as banking actions. Obtain the specific customer confirmation required by the applicable branch before executing it.

## Retrieve the affected debit cards

The customer need not know account IDs or card last-four digits.

1. Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified user's ID.
2. Limit debit-card retrieval to checking accounts. For every checking account returned, unlock and use `get_debit_cards_by_account_id_7823` with that account ID.
3. Match cards to the customer’s descriptions using account labels/classes when returned, card last four, and the customer’s confirmation. If labels are unavailable or ambiguous, present only the minimum safe identifiers needed (for example, account type/class and card last four) and ask the customer to identify the affected cards.
4. Include all identified cards in the review. A closed card may be historical; do not mistake it for a currently usable card.
5. Record the merchant/context and approximate time for each decline when available. If the issue persists, collect screenshots, exact timestamps/workflow, device/browser/app version, and escalate with logs after repeated failures.

## Required CODE 05 investigation order

For **each** affected card, use the following order. Do not skip directly to a fraud or velocity action.

1. **Card status**
   - `FROZEN`: Explain that the card is frozen and ask whether the customer wants it unfrozen. Only after explicit consent, confirmed ownership, verified identity, and confirmation that the linked checking account is `OPEN`, unlock/use `unfreeze_debit_card_3893` with the card ID. Confirm success.
   - `CLOSED`: Explain that the card is no longer active. Check for another active/pending card on the same account. Offer a replacement only through the separate replacement/order workflow; do not order automatically.
   - `PENDING`: The card is not activated. Follow the applicable activation procedure; do not represent it as usable before activation.
   - `ACTIVE`: Continue to account status.
   - Missing or unrecognized status: do not infer a cause. Re-query/inspect the card record or escalate a technical system error if status cannot be obtained.

2. **Linked checking-account status**
   - If the linked account is not `OPEN`, do not disclose the particular restriction for `SUSPENDED` or `RESTRICTED` accounts. Tell the customer exactly: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
   - Do not clear card protections or unfreeze the card while the linked account is not open.
   - If `OPEN`, continue to fraud-alert review.

3. **Fraud alert**
   - Inspect `fraud_alert_active` and `alert_source` from the debit-card lookup response.
   - If no alert is active, continue to velocity-block review.
   - If an alert is `customer_initiated`, ask the customer to verify recent transactions. Clear it only after identity verification and the customer confirms the transactions are legitimate. Unlock and call `clear_debit_card_fraud_alert_4892` using the card ID and `reason: "customer_verified"`. Document the confirmation and why it was cleared. If transactions are not recognized, do not clear; transfer to security.
   - If an alert is `bank_initiated`, never attempt to clear it. Tell the customer: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Then use `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise factual summary.
   - If the source is missing or unclear, do not clear the alert; obtain the source or escalate to security.

4. **Velocity block**
   - If `velocity_blocked` is true, explain: “Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?”
   - Clear early only after verified identity and a reasonable explanation of the activity. Unlock and call `clear_debit_card_fraud_alert_4892` with the card ID and `reason: "velocity_clear"`. Document the explanation and clearance reason.
   - If the customer declines, cannot verify, or gives suspicious/inconsistent information, do not clear. For suspicious circumstances, transfer using `fraud_or_security_concern`.
   - If no velocity block is active and all earlier checks are clear, explain that no status, account, fraud-alert, or velocity-block cause was found. Capture the decline details and escalate repeated unresolved failures as `technical_system_error` when a system issue prevents completion.

## Multiple-card execution and communication

- Maintain a per-card checklist: card ID/last four, linked account ID, status, account status, fraud state/source, velocity state, outcome, and any required customer consent.
- Diagnose every card before giving a final summary. Do not clear, unfreeze, or replace all cards in bulk merely because they have a common customer.
- If one card has a bank-initiated alert or an unauthorized-transaction report, transfer the customer to security rather than attempting to bypass that protection. Include the affected card(s), observed state, and actions already attempted in the transfer summary.
- For an active replacement/order request, use the replacement policy separately: verify eligibility, account tier, account age/status/balance, active/pending cards, replacement history, applicable exact fees, delivery/design selection, address, and explicit confirmation before ordering.

## Optional deterministic triage helper

`scripts/triage_code05.py` converts already retrieved, non-sensitive card/account fields into ordered next-step recommendations. It does not query banking tools, verify identity, perform an action, or replace agent judgment.

Input on stdin:

```json
{
  "accounts": [{"account_id": "...", "status": "OPEN"}],
  "cards": [{"card_id": "...", "account_id": "...", "status": "ACTIVE", "fraud_alert_active": false, "alert_source": null, "velocity_blocked": false}]
}
```

Output is JSON with one `triage` item per supplied card. Invoke it after account/card lookup, then carry out only the recommendation that remains permitted by the verification and confirmation gates:

```sh
python3 scripts/triage_code05.py <<'JSON'
{"accounts":[],"cards":[]}
JSON
```

Validate that the output has one item per input card, each item preserves `card_id`, and its `next_step` is reviewed against the live records before any tool call. Missing fields are intentionally reported as inspection requirements rather than guessed.
