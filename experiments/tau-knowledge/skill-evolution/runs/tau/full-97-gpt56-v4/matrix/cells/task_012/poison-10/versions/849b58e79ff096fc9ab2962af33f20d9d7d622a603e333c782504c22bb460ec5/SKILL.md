---
name: travel-readiness-with-limited-card-support-information
description: Answer general international-card travel-readiness questions when the available card documentation supports fraud alerts but does not establish a travel-notification workflow, app path, form, deadline, or account-specific action. Also handle an explicit request for a human agent.
---

# Travel Readiness With Limited Card-Support Information

## Use and boundary
Use this Skill for a customer concerned that an international trip could cause card declines when the supplied evidence describes fraud protection and alerts but does not document travel notices. It gives general guidance; it does not establish that a particular customer, card account, app feature, form, or travel-notice service exists.

Read the current customer message, the supplied card documentation, and prior tool observations. Treat a name, destination, rough trip timing, or an unverified lookup as conversation context only. Do not use it as proof of account ownership or enrollment.

## Response procedure

1. **Answer the current general question without inventing a workflow.**
   - If documentation does not explicitly establish a travel-notification feature, app route, form, required dates, or advance-notice period, say that these details cannot be confirmed from the available information.
   - Do not say that a notification is required, unavailable, already set, scheduled, unnecessary, or sufficient to prevent a decline.
   - Do not make up a URL, app menu, form name, deadline, availability rule, or country-specific authorization policy.

2. **Give only documented readiness measures.** If supported for the relevant card, recommend enabling transaction and international-use alerts and keeping contact details current. Explain that monitoring may flag unusual activity and request verification, so current contact information and prompt responses can help the customer address an alert. This is not a guarantee that all purchases will be approved.
   - Quote a fraud-alert response target only if it appears in the supplied evidence, and present it as a target, not a guarantee.
   - Mention other benefits (purchase protection, locking a card, replacement) only if documented and useful to the question.

3. **Handle unfinished itineraries.** Do not ask the customer to guess dates or record tentative dates merely to provide general information. If dates are not final, say they can check the issuer's current card-management support after finalizing the itinerary to learn whether an option exists and what information or timing it requires. This is a suggestion to verify, not a claim that an option is available.

4. **Keep general support separate from account actions.** A general answer does not require a lookup or collection of personal data. Do not repeat a request for email or identity fields that the customer declined. If the customer later requests an account-specific action, use only the declared banking tools and complete the declared identity-verification prerequisites before accessing or changing account information.

5. **Honor a direct request for a person.** When the customer explicitly asks to be transferred to a human agent, call `transfer_to_human_agents` rather than continuing to speculate about an undocumented workflow. Use `customer_requests_human_no_specific_reason` when no more specific documented transfer reason applies. Give a short factual summary: the customer seeks travel-notification/app/timing information, the available card documentation does not specify that workflow, and any already completed lookup or verification status. Never include unverified personal details in the transfer summary.

## Answer template
Adapt this to the evidence and latest turn:

> I can provide general travel-readiness information. The information I have does not confirm whether a travel notification can be submitted in the app, whether a form is needed, or how far ahead it must be done. When your itinerary is final, check the issuer's current card-management support to confirm whether a travel-related option is available and its requirements. In the meantime, enable transaction and international-use alerts and keep your contact details current, because unusual activity may prompt a verification request. These steps can help you respond quickly, but they cannot guarantee approval of every transaction.

If the customer requests a human agent after this answer, transfer them as described above.

## Pre-send checklist

- The answer addresses the actual question about app, form, dates, or lead time and labels unavailable details as unavailable.
- It does not imply that a travel notification was created or that the customer has an identified card account.
- Every factual card feature is present in the supplied documentation.
- It does not ask for unnecessary personal data or retry a declined request for it.
- It makes no promise of uninterrupted international card use.
- An explicit human-transfer request is actioned with the declared transfer tool and an applicable reason.
