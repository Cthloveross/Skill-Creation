---
name: international-card-travel-readiness
version: 1.0.0
description: Provide accurate, non-transactional guidance to a Rho-Bank Platinum Rewards Card customer preparing to use their card internationally, especially when they ask about travel notifications, app navigation, dates, alerts, and avoiding fraud-related declines. Use when the available evidence documents international-use alerts and fraud monitoring but does not document a specific travel-notification workflow.
---

# International Card Travel Readiness

## Purpose
Help a cardholder prepare for international card use without inventing an app feature, travel-notification form, required fields, or an account-specific status. This Skill is advisory only: it does not create travel notifications, change card settings, inspect accounts, or verify identity.

## Grounded facts
Use only the following established facts:

- International restrictions can cause a card transaction to be declined and may need to be lifted before international travel.
- Platinum Rewards Card fraud monitoring can flag unusual transactions and request cardholder verification.
- Platinum Rewards Card best practices include enabling transaction alerts and international-use alerts, and keeping contact details current.
- The Platinum Rewards Card charges no foreign transaction fee for international purchases.
- A cardholder can contact customer service or use mobile-app chat for help with card issues.

Do **not** state or imply that:

- a Travel Notification/Travel Plans feature definitely exists;
- the bank requires trip dates, dates are optional, or a notification can be submitted without dates;
- a particular menu path, field, approval result, international restriction, card status, or travel notice has been confirmed;
- the card will not be blocked or that a transaction will be approved.

## Conversation method

1. **Identify the immediate question.** Distinguish between (a) how to locate a possible in-app setting, (b) whether dates are required, and (c) general readiness for international use.
2. **Answer the navigation question first.** If the customer asks whether to look in Card Controls or Security Settings, advise them to start with **Card Controls** for the selected card. If no travel-related option is present, check **Security Settings** and the app's alert settings. Phrase this as a practical search order, not as a claim about the app's actual layout.
3. **Be transparent about dates.** Explain that the available information does not establish whether a travel-notification option exists or what fields it requires. Ask the customer to report what the app displays, especially whether it asks for destination and departure/return dates. Do not demand exact dates merely to provide general guidance.
4. **Offer grounded readiness steps.** Recommend enabling transaction and international-use alerts and confirming contact details are current so verification prompts can be received. Explain that unusual overseas activity may still prompt fraud verification. Mention the absence of a foreign transaction fee only when useful, while clarifying it does not guarantee authorization.
5. **Give a safe fallback.** If the option is absent, dates are required but not yet known, or the customer wants confirmation of an international-use restriction, direct them to customer service or mobile-app chat. State that support can review holds/restrictions and help with card issues; do not claim they will waive a date requirement.
6. **Do not request identity data or perform account lookup** just to explain the process. Account verification is not necessary for general navigation guidance.

## Recommended response shape

For a customer with app access who has not finalized dates, provide a concise response like this, adapted to their wording:

1. Confirm that they should open the relevant card in the mobile app and start with **Card Controls**.
2. Say to look for a label such as “Travel Notification” or “Travel Plans”; if it is not there, check **Security Settings** and alerts.
3. State that the documented information does not confirm whether that option exists or whether it requires dates. Ask them to note the fields shown, particularly destination and departure/return dates.
4. Tell them they can still prepare now by enabling transaction and international-use alerts and checking that their contact details are current.
5. Explain briefly that international activity can trigger fraud verification even when prepared, and that there is no foreign transaction fee for this card.
6. Offer in-app chat or customer service if they cannot find the setting, need a restriction reviewed, or the app requires information they do not yet have.

## Handling follow-ups

- If the customer says they found a form, explain only the fields they report seeing. Do not infer unreported fields or submission requirements.
- If they ask whether a two-week or future trip is acceptable, say that duration alone is not documented as a requirement; the displayed form or support can confirm its requirements.
- If they ask whether the card is active or unrestricted, explain that this cannot be determined from general guidance. Offer the supported service channels rather than claiming to check it.
- If they report a decline abroad, suggest checking card details and activation/expiration where relevant, retrying a possible temporary issue, and promptly contacting support to review potential restrictions or fraud alerts.

## Validation before sending

Ensure the response:

- directly answers the customer's latest question;
- labels unverified app behavior and date requirements as unknown;
- contains no fabricated app menu, policy, account result, or completed action;
- includes useful international-alert/contact-detail preparation;
- does not request a user ID or sensitive identity information for a general process question;
- offers mobile-app chat or customer service as the escalation path when necessary.

## Runtime use

Read the current customer opening and clarification history supplied in the public task input. Respond in conversational prose; no script or banking tool is needed for advisory travel-readiness requests. If a later request asks for an actual account change, use only a documented, declared banking workflow after satisfying its stated prerequisites. This Skill itself authorizes no account action.
