---
name: international-card-travel-readiness
version: 1.0.0
description: Respond safely to a Platinum Rewards Card holder who is preparing for international travel, especially when they ask about travel notifications but their itinerary is incomplete. Use this when the available product material documents fraud monitoring, alerts, contact details, and foreign-transaction fees, but does not document a notification workflow.
---

# International Card Travel Readiness

## Purpose
Give a concise, evidence-grounded customer-service response about preparing a Platinum Rewards Card for travel. Do not invent a travel-notification form, app workflow, required lead time, or a completed notification when the supplied product information does not establish those facts.

## Runtime input
Read the current conversation/public inputs supplied by the host. Extract:

- the customer's destination(s), approximate or exact travel dates, and whether dates are final;
- the card/product named by the customer;
- the customer's direct questions and any stated preference to wait; and
- prior clarifications, so already-answered questions are not repeated.

Use `references/product_facts.md` as the authority for available product facts.

## Method

1. **Determine whether an action can be supported.**
   - If the customer asks how to submit a travel notification, whether it can be done in an app, whether there is a form, or how far ahead it must be set up, check the reference.
   - The reference does not establish any travel-notification submission process, channel, lead time, or requirement. State that limitation plainly; do not claim that a notification is unnecessary.
   - Do not use account lookup, identity verification, logging, card controls, or discoverable tools merely to answer this informational question. Do not say an action was taken.

2. **Address incomplete itineraries accurately.**
   - If dates are not final, acknowledge that the customer can keep the itinerary details available once finalized.
   - Do not request the same dates again if the customer has already said they will wait. Do not imply that approximate dates have been submitted or recorded.
   - If exact dates are known, they may be restated as a travel-planning detail, but do not submit, log, or characterize them as a notification without an established workflow.

3. **Offer only supported travel-readiness guidance.**
   Include the relevant facts below, phrased naturally rather than as an exhaustive product summary:
   - The card has real-time fraud monitoring; unusual transactions may prompt the cardholder to confirm or deny a charge.
   - The customer should enable transaction and international-use alerts and keep contact details current so time-sensitive prompts can reach them.
   - Denying a risky charge causes it to be declined and can secure the card while it is investigated.
   - The product has a 0% foreign transaction fee for international purchases.
   - If relevant, the customer can temporarily lock a misplaced card and unlock it when found; a suspected compromise can prompt replacement of the card number.

4. **Answer the actual question directly.**
   - Lead with the unsupported-process limitation if that is the principal question.
   - Then give the supported practical steps and the foreign-fee information if the customer is traveling abroad.
   - Be careful to distinguish fraud alerts from a travel notification.
   - Avoid promises that the card will not be declined or blocked; monitoring may still prompt verification.

5. **Close constructively.**
   Explain that once dates are finalized, the customer should use an official account/support channel to confirm any current travel-notification procedure, because the supplied material does not specify it. This is a recommendation to confirm process, not a claim that a particular channel supports submission.

## Response requirements

- Use a helpful, customer-facing tone.
- Do not expose internal evidence, tool names, or this Skill.
- Do not fabricate account-specific information or claim to see the customer's card/account.
- Do not give unsupported timing, paperwork, app-navigation, eligibility, or coverage assurances.
- Do not ask for sensitive identity fields unless a subsequent supported account action actually requires verification.
- If the customer explicitly requests a human after the answer, use the normal transfer tool with the applicable allowed reason; otherwise an informational response does not itself require transfer.

## Optional deterministic helper

`scripts/assess_itinerary.py` accepts JSON on stdin and emits JSON on stdout. It performs only itinerary-state classification; it neither contacts the bank nor submits a notification.

Input schema:
```json
{"dates_final": false, "destinations": ["string"], "customer_will_wait": false}
```

Output schema:
```json
{"itinerary_status":"finalized|pending", "destination_status":"provided|not_provided", "should_repeat_date_request":false, "next_step":"string"}
```

Example runnable call in a supported script runtime:
```text
python scripts/assess_itinerary.py <<'JSON'
{"dates_final": false, "destinations": ["Japan"], "customer_will_wait": true}
JSON
```

Validate that the output is valid JSON, `itinerary_status` matches `dates_final`, and `should_repeat_date_request` is false when the customer has said they will wait. The helper's result does not establish a travel-notification policy; apply the evidence limitations above.
