---
name: unverified-credit-card-flyer-offer
version: 1.0.0
description: Handle a prospective credit-card applicant who wants to redeem a mailed promotional offer but cannot provide a customer record or any offer, invitation, expiration, or routing identifier. Use when the available card documentation establishes invitation-only eligibility but does not verify the external flyer or its terms.
---

# Unverified Credit-Card Flyer Offer

## Purpose

Provide an accurate, privacy-respecting response when a caller asks to redeem a credit-card flyer offer that cannot be matched to an account or verified invitation. Do not invent an application path, offer code, expiration date, eligibility decision, statement credit, or promotion terms.

## Inputs to assess

At runtime, use only the caller's statements, the available customer lookup results, and the packaged knowledge available to the agent. Identify whether all of the following are absent or unavailable:

- a customer/user ID or account-linked email that locates a record;
- an invitation or offer code, mailing/reference ID, barcode/QR data, dedicated application URL or phone number;
- an expiration date or applicable offer terms; and
- identifying addressee information the caller is willing to provide for invitation matching.

Treat a flyer with no verifiable identifier as an **unconfirmed external communication**. A caller's recollection of an offer is not sufficient to confirm that the offer is active, applicable, or redeemable.

## Procedure

1. **Do not repeat exhausted collection requests.** If the caller has already said that they have no account details and no flyer identifiers, or declined to provide addressee details, acknowledge that limitation rather than asking again for the same information.
2. **State the limitation plainly.** Explain that the offer cannot be located or verified without a matching customer record or invitation/offer identifier, so it cannot be redeemed or promised in the current interaction.
3. **Do not make account or promotion changes.** Do not log identity verification, change customer information, access account details, enroll the caller, apply a credit, or claim that spending will earn a credit. A prospect without a located record has not been identity-verified.
4. **Give only supported product context when relevant.** If the caller is asking about the Diamond Elite Card, explain that membership is invitation-only. The published consideration guidance says applicants should maintain a credit score of at least 780; timely payments, low utilization, verifiable income, and relationship depth may be considered. These are not a guarantee of an invitation. Invitations are time-limited.
5. **Avoid unsupported alternatives.** Do not direct the caller to a generic application link, telephone number, or a purported way to recreate the offer unless such information is explicitly available in the runtime knowledge.
6. **Escalate the unresolved flyer.** Since the external communication cannot be confirmed and the caller is seeking redemption, transfer to a human agent with reason `unconfirmed_external_communication`. The transfer summary must be factual and must not include unprovided sensitive data.

## Suggested customer-facing wording

> I understand you want to use the statement-credit offer shown on the flyer. Because I cannot match the flyer to a customer record or verify an invitation or offer identifier, I cannot confirm that the offer is active or apply it. I also cannot promise the statement credit based on the flyer alone. For context, Diamond Elite membership is invitation-only; maintaining a score of at least 780 is guidance for consideration, not a guarantee of an invitation. I will connect you with a specialist to review the unverified mailing.

Adapt this wording to the caller's request. Do not present the illustrative flyer terms as bank-confirmed terms.

## Required transfer action

Call `transfer_to_human_agents` exactly once after communicating the limitation when escalation is required. Use:

- `reason`: `unconfirmed_external_communication`
- `summary`: a concise statement such as: `Prospective applicant requests redemption of a mailed credit-card statement-credit offer. No customer record was located or supplied, and caller cannot provide an offer code, expiration date, mailing/reference ID, routing information, or addressee details for verification. Offer could not be confirmed or applied.`

If a future caller supplies verifiable information, first follow the then-available verified offer/application process; do not use this Skill to infer validity from the flyer text alone.

## Completion checks

Before finishing, confirm that the response:

- does not assert that the flyer offer exists, applies, is expired, or will be honored;
- does not promise a statement credit or eligibility;
- distinguishes invitation-only Diamond Elite guidance from a verified offer;
- does not treat a missing customer record as proof of ineligibility;
- does not request already-declined or already-unavailable details again; and
- transfers the unconfirmed external communication using the specified reason when the caller still seeks resolution.
