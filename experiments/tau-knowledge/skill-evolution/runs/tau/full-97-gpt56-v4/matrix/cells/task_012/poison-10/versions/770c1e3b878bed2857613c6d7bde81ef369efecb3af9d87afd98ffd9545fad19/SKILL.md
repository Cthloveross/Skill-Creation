---
name: travel-readiness-with-limited-card-support-information
description: Safely answer a cardholder's general pre-travel question when account lookup, travel-notification workflow, app availability, lead times, or enrollment actions are not supported by the available evidence. Use for requests to avoid card declines while travelling internationally.
---

# Travel Readiness With Limited Card-Support Information

## Purpose
Provide helpful, accurate general travel-readiness guidance without inventing an app flow, form, deadline, travel-notification capability, account status, or card-specific policy. This Skill is particularly appropriate when the customer has not finalized dates or declines to provide information needed to locate an account.

## Inputs to review
Use the live conversation, supplied knowledge documents, and any already completed tool observations. Identify:

- The destination and whether international card use is involved.
- Whether exact trip dates are available.
- Whether the customer is asking for a general answer or for an account-specific action.
- The card benefits and procedures explicitly supported by the supplied documents.
- Whether account lookup or identity verification has already failed or is incomplete.

Treat a customer name, destination, and tentative timing as private conversation context, not as evidence that an account has been located or that a notification was placed.

## Method

1. **Answer the latest question directly.** If the customer asks whether a notification can be set in an app, whether there is a form, or how far in advance it must be set, state only what the available evidence supports.
   - If no evidence establishes the workflow, do not claim that an app notification feature, form, lead time, or travel-notification service exists.
   - Say plainly that you cannot confirm the specific app/form process or required advance notice from the information available.
   - Do not imply that a notification has been created, scheduled, or is unnecessary.

2. **Use supported protective guidance.** When the supplied card information supports it, explain that the customer should enable transaction and international-use alerts and keep contact details current. Explain why: real-time monitoring can flag unusual transactions and may request verification; responding to those prompts can help resolve a flagged transaction. Do not promise that this will prevent every decline.

3. **Address unfinished dates safely.** If dates are not final, acknowledge that no dates need be guessed or recorded. Tell the customer to revisit the issuer's current card-management channels once their itinerary is finalized to confirm any available travel-related option and its timing. This is guidance to verify availability, not a representation that the option exists.

4. **Preserve account and verification boundaries.** General guidance does not require searching for another identifier or collecting personal data. If an account-specific request is made later, follow the declared verification process and only use normal banking tools after the necessary identity requirements are satisfied. Do not expose, infer, or alter account details based on a name alone.

5. **Close with an accurate next step.** Offer help with the documented alert and fraud-protection information or invite the customer to return with finalized itinerary details if a supported account workflow becomes available. Do not transfer merely because the workflow is undocumented. When the customer explicitly requests a human agent, use `transfer_to_human_agents` with the applicable reason. If no more specific reason is documented, use `customer_requests_human_no_specific_reason`; give a factual, minimal summary without unverified personal data. After a successful transfer, send a brief confirmation that the customer is being connected and then stop.

## Required response qualities

- Be concise, reassuring, and transparent about uncertainty.
- Separate documented facts from unavailable account-specific information.
- Do not fabricate a URL, menu path, form name, deadline, enrollment confirmation, card status, or country-specific authorization rule.
- Do not promise uninterrupted international use or guarantee that fraud controls will not block a transaction.
- Do not repeat requests for email or other identity fields when the customer has declined them and only seeks general guidance.

## Supported facts checklist
Only include an item when it is present in the supplied evidence for the relevant card:

- Transaction and international-use alerts are recommended.
- Keeping contact details current helps the cardholder receive time-sensitive verification prompts.
- Monitoring may flag unusual transactions and ask the cardholder to confirm or deny a charge.
- If the evidence documents it, a stated fraud-alert response target may be quoted exactly as a target, not a guarantee.
- Denying a suspicious charge can result in the transaction being declined and the card being secured while investigated.
- A misplaced card can be temporarily locked and later unlocked; suspected compromise can warrant replacement.
- Any stated purchase-protection window may be quoted only exactly as documented and only when relevant.

## Example response structure
Adapt this structure to the actual evidence and conversation; do not treat it as proof of an app feature:

> I can help with general travel readiness. I can't confirm from the information available whether travel notifications can be submitted in the app, whether a form is required, or how far ahead one must be submitted. Once your dates are final, check the issuer's current card-management options to confirm whether such an option is available and any timing requirement. In the meantime, enable transaction and international-use alerts and make sure your contact details are current, since unusual activity may trigger a verification prompt. These measures can help you respond quickly, but they do not guarantee that every transaction will be approved.

## Validation before sending
Confirm that the response:

1. Answers each explicit question about app access, a form, and advance timing without unsupported claims.
2. Does not say or imply that a travel notification was created.
3. Does not claim account ownership, card enrollment, or an account lookup result not established by tools.
4. Includes only card protections and recommendations supported by the current evidence.
5. Does not request unnecessary personal data for a general informational answer.
6. On an explicit request for a person, performs the declared transfer with an applicable reason and sends the brief connection confirmation.
