---
name: international-card-travel-readiness
version: 1.0.0
description: Guide a cardholder preparing for international travel when they ask about a travel notification, international-use controls, or avoiding an overseas decline. Use when the available product material confirms alerts or card controls but does not document a specific in-app form or setting.
---

# International Card Travel Readiness

Use this Skill to provide accurate, non-speculative self-service guidance for an upcoming international card trip. It is designed for cases where travel dates may be incomplete and the product material does **not** establish that a travel-notification form exists or that an agent can place one.

## Grounded facts to communicate

For the Platinum Rewards Card evidence provided with this task:

- International-use alerts are a fraud-protection best practice.
- Card/account controls and alerts are available through the account.
- International restrictions can cause a decline and may need to be lifted before travel.
- Unusual transactions can prompt a verification request; keep contact details current and respond promptly.
- The Platinum card's foreign-transaction fee is 0%, but this does not prevent merchant conversion charges or network exchange-rate effects.

Do not claim that a particular toggle, form, menu label, or agent-side travel-notification workflow exists unless the user can see it or an applicable source explicitly documents it.

## Method

1. Identify the destination and whether dates are known. If dates are not finalized, do not invent dates. A rough duration/month is enough to start checking controls, but exact dates may be required if the displayed control requests them.
2. Direct the customer to open the relevant card, then look under **Card Controls**, **Security**, or **Alerts** for labels such as **International Use**, **International Alerts**, **Travel Alerts**, or **Travel Notification**. Phrase these as places/labels to look for, not confirmed UI.
3. If the customer finds an international-use or travel setting, tell them to follow the fields shown, use their eventual dates if requested, and ensure Japan/international use is enabled only if that is what the control offers.
4. If there is no such setting, do not imply failure or invent a form. Recommend customer service to check whether an international restriction or fraud alert needs attention before departure.
5. Recommend alerts and current phone/email so the cardholder can receive a verification request. Remind them to retain receipts and carry a backup payment method.
6. Explain that a 0% bank foreign-transaction fee does not guarantee that a merchant will not offer dynamic currency conversion or impose its own charges. Advise comparing totals and considering local currency where appropriate.
7. If the transcript ends because the customer cannot complete the requested app lookup (for example `OUT-OF-SCOPE`), give the navigation again as the next customer action. Do not treat it as confirmation that the setting is absent.

## Safety and boundaries

- This is guidance only. Do not represent that a notification was created, an international restriction was changed, or the card is guaranteed not to decline.
- Do not ask for card number, CVV, password, or other sensitive credentials.
- Do not perform account lookup, identity verification, or banking actions merely to give navigation.
- Do not transfer solely because dates are unknown or because the setting has not yet been checked. Escalate to normal customer service only when the customer reports the setting is unavailable, a restriction/decline persists, or they need an account-specific review.

## Runtime helper

`scripts/travel_guidance.py` accepts JSON on stdin and emits JSON on stdout.

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

All fields are optional. `latest_lookup_status` can be `not_checked`, `found`, `not_found`, or `out_of_scope`. The helper does not access accounts or alter any card setting.

### Output schema

```json
{
  "recommended_message": "customer-facing guidance",
  "next_customer_action": "one concrete next action",
  "support_needed_if": "condition for account-specific help",
  "validation": {"valid": true, "issues": []}
}
```

Run it with the case facts, send `recommended_message` to the customer (editing only for known facts), and use `next_customer_action` to keep the interaction sequential. Validate that the resulting message does not assert that a form, setting, notification, or control change exists or was completed.

Example runnable invocation:

```bash
printf '%s' '{"destination":"Japan","trip_timing":"two-week trip next month","dates_known":false,"latest_lookup_status":"not_checked"}' | python3 scripts/travel_guidance.py
```
