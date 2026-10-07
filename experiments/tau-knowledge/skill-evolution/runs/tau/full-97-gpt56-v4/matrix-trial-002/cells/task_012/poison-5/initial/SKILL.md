---
name: international-card-travel-preparation
version: 1.0.0
description: Handle a cardholder's request to avoid international card declines before travel when the available support evidence confirms possible international restrictions and assistance channels, but does not confirm a self-service travel-notice workflow.
---

# International Card Travel Preparation

Use this Skill when a customer asks how to prepare an active card for travel abroad, set a travel notification, or prevent an international purchase decline.

## Method

1. Identify the destination and determine whether the customer has exact departure and return dates.
2. Confirm only facts supported by the supplied account/product context. Do not access account records, request identity verification, or perform account changes merely to provide general travel-preparation guidance.
3. If the card is not activated, explain that activation is needed before use. If it is already activated, acknowledge that prerequisite is complete.
4. Explain that international restrictions can apply to some cards, so the customer should arrange support before traveling to reduce the chance of a decline. Do not guarantee that a transaction will be approved.
5. If exact dates are unavailable, do not invent dates or claim a notice has been submitted. Tell the customer to return once the itinerary is confirmed with the destination plus exact departure and return dates.
6. State the supported assistance routes: customer service at `1-800-RHO-BANK`, chat through the Rho-Bank mobile app, or `rhobank.com/help`.
7. When asked whether the app itself has a self-service travel-notification feature, distinguish app chat from a self-service feature: the evidence supports app chat as an assistance channel, but does not establish a particular app menu or that a customer can independently submit a travel notice there. Recommend using app chat once dates are known.
8. Include any supported product-specific international-fee fact when relevant. Do not extrapolate this fact to other card products.

## Response requirements

Give a concise, customer-facing answer that:

- acknowledges the trip and the customer's goal;
- says the activated-card prerequisite is satisfied when that has been confirmed;
- accurately describes the missing itinerary dates as the remaining information needed to request/review travel-related support;
- offers the supported app-chat, phone, and help-site routes;
- avoids promises of successful transactions, automatic enrollment, or a confirmed travel-notice feature;
- mentions the card's foreign-transaction fee only where the supplied product facts establish it.

## Handling unavailable details

If dates are missing, a suitable response is to say that the customer does not need to finalize anything right now, but should contact support through mobile-app chat (or the phone/help site) after the itinerary is confirmed and provide the Japan destination and exact dates. Phrase this as requesting travel-related support or a review of international restrictions, rather than claiming that a notification has already been set.

If the customer supplies exact dates later, direct them to the same supported channel and have them provide the destination and dates. Do not make unsupported claims about form fields, lead times, a confirmation number, or an internal travel-notice tool.

## Known supported facts for the supplied Platinum Rewards context

- The Platinum Rewards Card must be activated before use.
- Its foreign transaction fee is 0% on international purchases.
- Some cards can have international restrictions that may need to be lifted before travel.
- For card issues, assistance is available through customer service, mobile-app chat, and the help website.

## Validation checklist

Before sending the answer, verify that it does not:

- state or imply that a travel notification was created without confirmed dates and an actual supported action;
- represent app chat as a verified self-service travel-notice workflow;
- request sensitive identity fields unnecessarily;
- guarantee that the card will not be blocked or that foreign transactions will be approved;
- confuse a 0% foreign transaction fee with exchange-rate treatment or merchant charges.
