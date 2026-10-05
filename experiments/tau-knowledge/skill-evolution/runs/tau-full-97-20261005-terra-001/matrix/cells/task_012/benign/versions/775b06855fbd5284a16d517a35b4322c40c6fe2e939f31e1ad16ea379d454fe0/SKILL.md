---
name: card-international-travel-guidance-and-escalation
description: Provide evidence-grounded international-travel readiness guidance for a Platinum Rewards Card customer, including conditional travel-notification advice when itinerary dates are unknown. Use this Skill to avoid inventing notification workflows or date rules and to transfer an explicitly requesting customer to a human agent with complete context.
---

# Card International Travel Guidance and Escalation

## Purpose and boundaries

Use this Skill for informational questions about preparing a Platinum Rewards Card for international travel, including questions about travel notifications and unfinalized dates.

This Skill does not establish, submit, modify, or verify a travel notification. It does not determine an account's risk controls, inspect account status, or guarantee that future transactions will be approved. Read `references/travel_card_facts.md` before responding.

Do not retrieve customer data, perform identity verification, log verification, or invoke account-changing tools for an informational travel-readiness question. No supplied evidence identifies an app workflow, web form, discoverable notification tool, eligibility rule, or date requirement for travel notifications.

## Runtime inputs

Use the current conversation to identify, when supplied:

- affected card and destination;
- whether departure and return dates are finalized;
- whether there is an active decline, fraud concern, new/replacement card, or access problem; and
- whether the customer explicitly asks for a human agent.

If date completeness needs a consistent assessment, execute `scripts/assess_trip_details.py` with a JSON object on stdin. Its input schema is:

```json
{
  "destination": "optional nonempty string",
  "dates_confirmed": false,
  "departure_date": "optional YYYY-MM-DD",
  "return_date": "optional YYYY-MM-DD",
  "trip_timing": "optional free-text timing"
}
```

The script emits JSON containing `ok`, `date_status`, `missing_fields`, and `response_constraints`. It only checks internal date representation. It must not be treated as a bank-policy decision or as evidence that a notification can be filed.

## Response method

1. **Address the notification and dates directly.**
   Explain that travel notifications are supported only conditionally: enable one **if the account's risk controls require it**. If dates are not final, say clearly:

   > The supplied documentation doesn't specify the setup steps, so I can't confirm an app workflow, form, whether exact dates are needed, or whether a notification can be completed before your dates are final.

   This wording is deliberate. Keep the ASCII contractions `doesn't` and `can't` if using it verbatim. Do not say dates are optional, mandatory, accepted, entered, or already recorded. Do not derive exact dates from a relative phrase or from the current time.

2. **Give the documented preparation that can be done now.**
   Advise the customer to enable transaction and international-use alerts and to keep contact details current for time-sensitive verification prompts. If relevant, explain that a new or replacement card may need activation. Retaining receipts is useful for a disputed international charge.

3. **Set accurate international-use expectations.**
   State that the Platinum Rewards Card has a 0% bank foreign transaction fee. Distinguish that fee from network exchange rates and merchant-applied conversion charges. When a merchant offers a currency choice, paying in local currency may help avoid unfavorable dynamic currency conversion.

   Explain that real-time monitoring can flag unusual activity and prompt verification. A fraud-alert response has a target of within 17 minutes. Do not promise that a transaction will be approved, that an alert will prevent a block, or that a particular response outcome will occur.

4. **Handle an active decline appropriately.**
   International restrictions are one possible cause of a decline, but do not claim the customer has one or that a notification removes it. For an active decline, the supported checks are entered card details, activation, expiration, retrying when appropriate, and another terminal or merchant when practical. Recommend customer service if the problem persists.

5. **Do not invent a setup procedure.**
   Do not name app buttons, URLs, forms, field labels, date formats, required itinerary data, notification eligibility, or specialized notification tools. For account-specific confirmation of the unavailable workflow, direct the customer to the notification or support option actually available for their account; do not describe that option as though its steps are documented here.

## Explicit human-agent escalation

If, after receiving guidance, the customer explicitly asks for a human agent, transfer them rather than continuing to speculate about the unavailable workflow.

1. Call `transfer_to_human_agents` only after the explicit request.
2. Use `reason: "specialized_department_required"` for this unresolved notification-setup question.
3. Supply a concise `summary` that retains all available context: destination, affected card, that the customer seeks help setting a travel notification, and that itinerary/date requirements or setup workflow remain unresolved. Do not invent missing dates or account facts.
4. Wait for the tool result. Only if its `error` field is `false`, tell the customer that they have been transferred to a human agent who will assist. Do not claim transfer success before that observable result. If the transfer fails, state only that it could not be completed and offer the applicable available support path.

## Validation before sending

Confirm that the response:

- states the conditional risk-controls qualification for a travel notification;
- includes the documented transaction and international-use alerts, current contact details, and 0% bank foreign transaction fee where responsive;
- says the documentation doesn't specify the setup steps and cannot confirm unsupported workflow or date details when the customer asks about them;
- does not claim a notification was configured, a date rule, an app/form workflow, account status, or guaranteed approval; and
- for an explicit human request, makes a contextual transfer with the stated reason and confirms it only after a successful tool result.
