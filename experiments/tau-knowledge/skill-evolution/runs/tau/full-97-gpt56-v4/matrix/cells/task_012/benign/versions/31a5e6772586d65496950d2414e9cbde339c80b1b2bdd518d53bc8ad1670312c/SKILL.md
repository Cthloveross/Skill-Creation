---
name: international-card-travel-guidance
description: Respond safely to a cardholder asking how to avoid international credit-card declines or set up a travel notification, when the available policy confirms international restrictions and support channels but does not document a self-service notification workflow.
---

# International Card Travel Guidance

Use this Skill for informational questions about using a credit card abroad, particularly travel-notification questions.

## Method

1. Identify whether the customer is asking for general guidance or requesting an account-specific change.
2. State only supported facts from `references/policy.md`:
   - international restrictions can contribute to declines;
   - the Platinum Rewards Card has no foreign transaction fee on international purchases;
   - support can review holds, restrictions, and fraud alerts through phone, mobile-app chat, or website help.
3. Do **not** claim that travel notifications can be created in the app, that a form exists, that a particular lead time is required, or that dates can be saved before they are finalized unless current approved policy explicitly supplies those details.
4. If dates are not final, explain that the available material does not specify an advance-notice rule. Recommend contacting support once the itinerary is known to ask them to review applicable international restrictions. The customer may use mobile-app chat, the help website, or the support phone number documented in the reference.
5. Do not request account identifiers, retrieve account data, verify identity, or make account changes for a purely informational request. If the customer asks to perform an account-specific setup, follow the live workflow and authentication requirements available at execution time; do not invent a setup tool or form.
6. Mention the 0% foreign transaction fee only when relevant to the customer’s international-use question. It does not guarantee that a transaction will be approved.
7. If the card is declined while abroad, suggest checking entered card details, retrying a temporary failure, trying another terminal or merchant when practical, and contacting support to review restrictions or fraud alerts.

## Runtime helper

`scripts/build_travel_guidance.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:
- `dates_finalized` (boolean, optional): whether exact travel dates are known.
- `card_name` (string, optional): card name to mention; use only if supplied.
- `destination` (string, optional): destination to mention; use only if supplied.
- `asks_setup_method` (boolean, optional): whether the customer asks whether an app workflow or form exists.
- `asks_timing` (boolean, optional): whether the customer asks how far ahead to notify.
- `international_card` (boolean, optional, default `true`): whether the question concerns international card use.

Output schema:
- `response` (string): customer-ready, policy-bounded guidance.
- `unsupported_details` (array of strings): requested workflow details absent from the supplied policy.
- `next_step` (string): safe recommended next step.

Run it with a JSON object appropriate to the current conversation, then use its `response` as a draft. Confirm any live, approved workflow before stating account-specific instructions.

Example invocation shape (values are placeholders):

```sh
printf '%s' '{"dates_finalized":false,"asks_setup_method":true,"asks_timing":true}' | python3 scripts/build_travel_guidance.py
```

## Validation

The helper rejects a non-object JSON input and enforces boolean types for boolean fields. Before sending a response, check that it does not assert an undocumented app feature, form, advance-notice period, completed account change, or approval guarantee.