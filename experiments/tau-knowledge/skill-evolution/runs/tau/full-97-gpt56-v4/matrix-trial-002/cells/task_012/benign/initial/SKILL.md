---
name: travel-readiness-with-limited-card-policy
version: 1.0.0
description: Respond safely to a cardholder asking how to prevent international card declines when the available card documentation confirms fraud-alert and foreign-transaction-fee features but does not confirm a travel-notice workflow, channel, form, or timing. Use when no authorized account-action tool or documented travel-notice procedure is available.
---

# Travel Readiness With Limited Card Policy

## Purpose
Give a useful, accurate response to an international-travel question without inventing a travel-notification feature or attempting account changes that the available documentation and tools do not support.

## Runtime input
The executor receives the current customer conversation, including any clarifications, plus the packaged reference at `references/card_travel_facts.md`.

Optionally run:

```json
{"card_is_activated": true, "destination_known": true, "dates_known": false, "customer_can_check_app": false}
```

with `scripts/travel_readiness.py`. The script reads one JSON object from stdin and emits a JSON assessment on stdout. Its fields are booleans only; omit a field or use `null` when unknown.

## Procedure
1. Identify the actual request: setting a travel notification, avoiding an international decline, or both. Note whether the card is active and whether dates are finalized, but do not treat either fact as proof that a travel notice is required or available.
2. Use only the supported facts in the packaged reference. In particular, distinguish documented *international-use alerts* from an undocumented *travel notification*. Do not rename one as the other.
3. If no documented workflow exists, say plainly that the available information does not confirm:
   - a dedicated travel-notification option;
   - whether it is in the app, online banking, phone support, or a form;
   - any required travel dates or advance-notice period; or
   - that a travel notice is necessary to use the card abroad.
   Do not guess a menu path, channel, lead time, or form.
4. Give the documented, actionable preparation steps that remain useful: enable transaction and international-use alerts if the account offers them, verify contact information, and monitor/respond promptly to fraud-verification prompts. State that the card has 0% foreign transaction fees only when that card product is established by the conversation or context.
5. Explain the relevant protection behavior: unusual activity can prompt a confirm-or-deny alert; denying a charge causes it to be declined and can secure the card while it is investigated. Do not characterize this as a guarantee that legitimate foreign purchases will never be reviewed or declined.
6. When the customer declines to inspect the app, do not pressure them and do not ask again for the same check. Offer the documented readiness steps and candidly state the unresolved travel-notice question. If an approved support/escalation route is documented elsewhere in the active environment, use it only as documented; otherwise do not invent one.
7. Do not access customer records, request identity data, log verification, alter account settings, or transfer the customer solely for this informational request. Do not claim that any account change has been made.

## Response shape
Keep the response concise and customer-facing:

- Acknowledge the travel goal.
- State the travel-notification limitation directly.
- List the supported preparation steps.
- State the foreign-fee and fraud-alert facts relevant to the request.
- Separate unknowns from recommendations; do not imply completion of a notice.

## Validation
Before sending, verify each assertion against `references/card_travel_facts.md` and the live conversation. The response must not contain an asserted app path, form, phone number, notice lead time, travel-notice requirement, or completed account action unless independently documented in the active task environment. If the helper reports `travel_notice_workflow_documented: false`, it is invalid to say that the customer can set a travel notice through any particular channel.
