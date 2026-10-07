---
name: international-card-travel-readiness
version: 1.1.0
description: Guide a cardholder preparing for international travel when they ask about travel notifications, international-use controls, or preventing overseas card declines. Use when account controls and alerts are documented but the actual app UI and travel dates have not been confirmed.
---

# International Card Travel Readiness

Provide evidence-bounded, self-service guidance for an upcoming international trip. This Skill does not assume that a travel-notification form, toggle, or agent-side workflow exists.

## Grounded Platinum Rewards facts

- The Platinum Rewards Card has account alerts and digital/card controls available through the account.
- International-use alerts and transaction alerts are recommended fraud-protection preparation.
- Unusual transactions may generate a fraud-verification prompt. The cardholder should keep phone and email details current and respond **within 17 minutes** of a time-sensitive prompt.
- International restrictions can contribute to a decline and may need account-specific review before travel.
- The Platinum Rewards Card has a **0% Rho-Bank foreign transaction fee** on international purchases.

## Customer-facing method

1. Keep the response tied to the requested card and destination. For this case, refer to the **Platinum Rewards Card** and the trip to **Japan**.
2. Since exact dates are not confirmed, say that preparation can begin now. Do not invent travel dates or a form. Explain that dates should be entered **once confirmed** only if the actual displayed control requests them.
3. Direct the customer to open the relevant card in the mobile app or online account and look under **Card Controls first**, then **Security** or **Alerts**. Suggest possible labels to look for: **International Use**, **International Alerts**, **Travel Alerts**, or **Travel Notification**. These are labels to check for, not confirmed UI.
4. If an international-use or travel control appears, instruct the customer to follow only the fields actually shown and review the app or website confirmation before relying on it.
5. Recommend enabling transaction and international-use alerts, keeping contact information current, and responding to any fraud-verification prompt within the documented **17-minute response window**. Explain that reachable contact details are needed to receive and handle those prompts.
6. State the card-specific 0% Rho-Bank foreign transaction fee when relevant. Do not imply that this guarantees a particular merchant exchange rate or prevents all merchant/network charges.
7. Give a concrete fallback: **If you can't find** an International Use or Travel Notification setting, contact Rho-Bank **customer service**, use **in-app chat**, or visit **rhobank.com/help** for an account-specific review of possible international restrictions or fraud holds. Use the same path if the **card is declined abroad** or overseas despite available credit.
8. A backup payment method and retained receipts are prudent travel preparation, but do not claim the card cannot be declined.

## Boundaries

- Do not say that a notification was created, a restriction was lifted, or international use is guaranteed.
- Do not claim that a particular toggle, menu label, form field, or travel-notification workflow exists unless the customer sees it or an applicable source documents it.
- Do not request card numbers, CVV, passwords, or other sensitive credentials.
- Do not perform account lookup, identity verification, or card-control changes solely to provide navigation.
- An `OUT-OF-SCOPE` result for a requested app lookup is not confirmation that the setting is absent. Repeat the next one-at-a-time action: look under Card Controls first.

## Runtime helper

`scripts/travel_guidance.py` reads a JSON object from stdin and writes a JSON object to stdout. It only drafts guidance; it does not access accounts or execute banking actions.

### Input schema

```json
{
  "destination": "Japan",
  "trip_timing": "two-week trip next month",
  "dates_known": false,
  "latest_lookup_status": "out_of_scope",
  "include_fee_note": true
}
```

All fields are optional. `latest_lookup_status` must be one of `not_checked`, `found`, `not_found`, or `out_of_scope`.

### Output schema

```json
{
  "recommended_message": "customer-facing guidance",
  "next_customer_action": "one concrete next action",
  "support_needed_if": "conditions requiring account-specific support",
  "validation": {"valid": true, "issues": []}
}
```

Send `recommended_message` after checking it against facts actually known in the conversation. Use `next_customer_action` to preserve one-action-at-a-time navigation. If the helper reports invalid input, correct the listed fields before using the draft.

Example runnable invocation:

```bash
printf '%s' '{"destination":"Japan","trip_timing":"two-week trip next month","dates_known":false,"latest_lookup_status":"out_of_scope"}' | python3 scripts/travel_guidance.py
```
