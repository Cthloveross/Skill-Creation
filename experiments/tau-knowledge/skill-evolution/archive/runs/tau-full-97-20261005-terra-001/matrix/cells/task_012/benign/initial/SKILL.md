---
name: platinum-card-international-travel-guidance
description: Provide evidence-grounded guidance for a Platinum Rewards Card customer traveling internationally, especially when they ask about travel notifications before dates are finalized. Use it to distinguish documented card protections and preparation steps from unsupported claims about notification eligibility, dates, app navigation, or account changes.
---

# Platinum Card International Travel Guidance

## Purpose

Respond safely and directly to international-travel readiness questions for the Platinum Rewards Card. This Skill covers informational assistance only; it does not establish, modify, or submit a travel notification.

Use `references/travel_card_facts.md` as the factual source. It intentionally does **not** infer an app workflow, a required date format, or whether an unfinished itinerary is acceptable.

## Inputs

Collect only details relevant to the answer:

- Destination, if the customer provided one.
- Whether departure and return dates are finalized.
- Any reported problem, such as a declined charge, a suspected fraud alert, or a card that is new/replacement.

For a consistent assessment of date completeness, run `scripts/assess_trip_details.py` with JSON on stdin. Example input:

```json
{
  "destination": "Japan",
  "dates_confirmed": false,
  "trip_timing": "two-week trip next month"
}
```

The script emits JSON with `ok`, `date_status`, `missing_fields`, and `response_constraints`. It does not determine notification eligibility or perform a banking action.

## Method

1. **Acknowledge the travel goal and answer the date question.**
   If dates are not final, explain that the available materials do not state whether a travel-notification setup can be completed without exact departure and return dates. Do not say dates are optional, mandatory, already recorded, or that a notification has been set.

2. **State the documented preparation that can be done now.**
   For this card, the materials support advising the customer to:
   - enable transaction and international-use alerts;
   - keep contact details current so time-sensitive verification prompts can reach them;
   - make sure the card is activated if it is new or a replacement; and
   - retain receipts for any disputed international charge.

   The materials say to enable travel notifications **if the account's risk controls require them**. They do not provide the navigation steps, eligibility rules, or a date requirement. Tell the customer to use the account's available notification flow or contact card support to confirm the requirement and provide itinerary details once available; do not invent buttons, URLs, fields, or a specialized tool.

3. **Set accurate expectations about travel use.**
   Explain that the Platinum Rewards Card has a 0% bank foreign transaction fee. This does not eliminate network exchange rates, merchant conversion charges, or dynamic currency conversion. If offered a currency choice, paying in local currency may avoid unfavorable merchant conversion.

   Real-time monitoring can flag unusual transactions and request verification. A fraud-alert response is targeted within 17 minutes; advise the customer to monitor and promptly respond to legitimate verification prompts, without promising approval or an exact response outcome.

4. **Address decline risk without overpromising.**
   International restrictions can be one possible reason a card is declined. Do not state that the customer has such a restriction, that a travel notification lifts one, or that enabling alerts guarantees transactions will be approved. If a charge is declined, recommend checking card details/activation/expiry, retrying if appropriate, trying another terminal or merchant when practical, and contacting customer service if the issue continues.

5. **Keep operational boundaries explicit.**
   This request does not require identity verification or access to account data. Do not retrieve personal information, log verification, change account information, unlock an unspecified discoverable tool, or claim to have set a notification. No packaged evidence identifies a travel-notification tool, so do not guess one or pass an invented tool to the customer.

## Suggested response shape

Use a concise response such as:

> You can prepare now by turning on transaction and international-use alerts and making sure your contact details are current. The available card guidance says to enable a travel notification if your account's risk controls require it, but it does not say whether exact trip dates are required or provide the setup steps. Once your dates are set—or through the notification flow/support available for your account—confirm what itinerary details are needed. Your card has a 0% bank foreign transaction fee; choose local currency when offered a conversion choice, and watch for verification alerts while traveling.

Adapt this to the customer's supplied facts. Do not imply that an action was completed.

## Validation before sending

Check that the response:

- directly addresses whether unavailable dates can be resolved from the supplied documentation;
- identifies travel notifications as conditional on risk controls rather than guaranteed or unnecessary;
- includes only supported Platinum Card facts;
- avoids fabricated app instructions, date requirements, account status, and tool names;
- does not promise prevention of a block or approval of future transactions; and
- distinguishes the 0% bank foreign transaction fee from exchange rates and merchant conversion charges.

If the customer reports an active decline, fraud concern, or inability to access an account setting, pivot to the applicable troubleshooting or support path rather than treating this informational guidance as a completed account action.
