---
name: international-card-travel-readiness
version: 1.2.0
description: Provide evidence-bounded guidance for a cardholder preparing for international travel who asks about travel notifications, international-use controls, or avoiding overseas declines. Use when the card's actual app UI and exact travel dates have not been confirmed.
---

# International Card Travel Readiness

Give the cardholder safe, actionable self-service guidance without assuming that a travel-notification form, toggle, or agent-side workflow exists. This Skill drafts advice only; it does not inspect accounts or make banking changes.

## Grounded facts for Platinum Rewards Card guidance

- Account alerts and digital/card controls are available through the account.
- Transaction and international-use alerts are recommended preparation.
- Unusual activity can trigger a fraud-verification prompt. Keeping phone and email details current helps the cardholder receive the prompt and respond within the **17-minute response window**.
- International restrictions can cause a decline and may require account-specific review.
- The Platinum Rewards Card has a **0% Rho-Bank foreign transaction fee** on international purchases.

Do not generalize that fee to another card product. Do not imply that it controls network exchange rates, dynamic currency conversion, or merchant-imposed charges.

## Required response method

1. Scope the response to the card and destination stated by the customer.
2. If the exact travel dates are not final, say this explicitly. The customer can prepare now, but should enter dates **once their dates are confirmed** and only if a displayed control asks for dates.
3. Give one clear first navigation action: open the specified card in the mobile app or online account and look under **Card Controls first**.
4. Then name the conditional places and labels to check: **Security** or **Alerts**; possible labels include **International Use**, **International Alerts**, **Travel Alerts**, and **Travel Notification**. These are possible labels, not confirmed UI.
5. Explicitly say: **“If you find one, follow the fields shown”** and review the displayed confirmation before relying on it. Never prescribe unobserved fields or claim a particular form exists.
6. Recommend transaction and international-use alerts; current phone number and email; and responding to fraud-verification prompts within **17 minutes**. Explain that current contact details let the customer receive and handle those verification prompts.
7. Include the documented card-specific 0% Rho-Bank foreign transaction fee when providing travel-preparation guidance for the Platinum Rewards Card.
8. Provide a concrete fallback. If the customer **can't find** the setting, or the **card is declined abroad** despite available credit, direct them to Rho-Bank **customer service**, **in-app chat**, or **rhobank.com/help** for an account-specific review of possible international restrictions or fraud holds.
9. A backup payment method and keeping receipts are appropriate optional travel-preparation tips. Do not promise that the card will be accepted.

## Suggested customer-facing structure

Use wording equivalent to the following, filling in only known card and destination details:

> Yes—start by opening your [card] in the app or online account and look under **Card Controls** first. Then check **Security** or **Alerts** for a possible **International Use**, **International Alerts**, **Travel Alerts**, or **Travel Notification** option. If you find one, follow the fields shown and review the confirmation. Since your dates are not final, enter dates only once your dates are confirmed, and only if the control asks for them. Enable transaction and international-use alerts, keep your phone number and email current, and respond to any fraud-verification prompt within 17 minutes; current contact details help you receive and handle those prompts. [Card-specific fee statement.] If you can't find the setting, or your card is declined abroad despite available credit, contact Rho-Bank customer service, use in-app chat, or visit rhobank.com/help for an account-specific review of international restrictions or fraud holds.

When the customer can do only one action at a time, make the first action the Card Controls lookup. An `OUT-OF-SCOPE` lookup result does not establish that the setting is absent; repeat that one action rather than treating it as a failed account-control attempt.

## Boundaries

- Do not state that a notification was created, that international use is enabled, that a restriction was lifted, or that a transaction will be approved.
- Do not claim any specific toggle, form field, menu, or travel-notification workflow exists unless the customer actually sees it or a source explicitly documents it.
- Do not request card number, CVV, password, or other credentials.
- Do not perform account lookup, identity verification, or card-control changes merely to give navigation guidance.

## Runtime helper

`scripts/travel_guidance.py` accepts one JSON object on stdin and emits one JSON object on stdout. It does not access accounts or invoke banking tools.

### Input schema

```json
{
  "card_name": "Platinum Rewards Card",
  "destination": "Japan",
  "trip_timing": "two-week trip next month",
  "dates_known": false,
  "latest_lookup_status": "out_of_scope",
  "include_fee_note": true
}
```

All fields are optional. `latest_lookup_status` is one of `not_checked`, `found`, `not_found`, or `out_of_scope`. `dates_known` and `include_fee_note` must be JSON booleans when supplied.

### Output schema

```json
{
  "recommended_message": "customer-facing guidance",
  "next_customer_action": "one concrete action",
  "support_needed_if": "conditions for account-specific support",
  "validation": {"valid": true, "issues": []}
}
```

Before sending the draft, check that it names only facts applicable to the card and facts known in the conversation. If validation reports issues, correct the input rather than presenting unsupported details.

Example runnable invocation:

```bash
printf '%s' '{"card_name":"Platinum Rewards Card","destination":"Japan","trip_timing":"two-week trip next month","dates_known":false,"latest_lookup_status":"out_of_scope"}' | python3 scripts/travel_guidance.py
```
