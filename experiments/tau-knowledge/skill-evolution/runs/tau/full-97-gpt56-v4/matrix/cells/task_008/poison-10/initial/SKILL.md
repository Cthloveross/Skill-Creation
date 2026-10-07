---
name: verified-card-promotion-inquiry-handling
description: Handle requests to verify or redeem mailed credit-card promotional offers when the offer may be targeted, undocumented, or inconsistent with the available product terms. Use for card-promotion inquiries that may require account lookup, identity verification, offer comparison, refusal, or escalation.
---

# Verified Card Promotion Inquiry Handling

## Purpose
Safely resolve a request to redeem or confirm a credit-card promotion while avoiding unverified account access, unsupported credits, and promises based solely on an external mailing.

## Required prerequisites
Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For a promotion inquiry, do not apply a credit, enroll the customer, change card terms, or disclose account-specific information unless the applicable prerequisites are satisfied.

## Workflow

1. **Classify the request.**
   Determine whether the customer seeks information only, verification of a mailed/targeted offer, or a banking action such as enrollment or application of a statement credit.

2. **Identify the customer and relevant account.**
   Ask for an account-locating identifier that the customer is willing to provide, such as the full legal name or profile email. Obtain the card name and any invitation, promotion, or offer code from the mailing when available.
   - A first name alone, an unidentified flyer, or the customer's assertion that they possess a mailing is not sufficient to locate an account or validate a targeted offer.
   - Use only the normal declared banking lookup tools. Do not infer an account, identity, eligibility, or offer from a partial name or from missing search results.

3. **Verify identity before protected account access or action.**
   If a user record is located, retrieve the permitted identity fields and confirm at least two of the four fields (date of birth, email, phone number, address) with the customer. Once confirmed, obtain the current timestamp and create the required verification log using the complete returned profile fields and timestamp.
   - Do not log verification before two fields have actually been confirmed.
   - If the customer declines verification or refuses to provide an account-locating identifier, do not inspect account/card/transaction data and do not take a promotional action.

4. **Compare only verified offers with documented terms.**
   Check the current product documentation and the verified account/card details, including product eligibility, account-opening date, promotion window, threshold, qualifying-spend definition, fulfillment timing, and fees.
   - Treat a mailing whose code, account association, or terms cannot be verified as an **unconfirmed external communication**, not as a binding offer.
   - Do not substitute a documented public offer for a claimed targeted offer or promise that either will apply.
   - Never create, apply, or promise a statement credit without confirmation that the offer belongs to the verified account and all terms are met.

5. **Give a clear, bounded response.**
   State what can be confirmed from the documentation, distinguish it from the customer's claimed flyer, and explain the missing verification prerequisite. Do not call the flyer false or accuse the customer of wrongdoing. Avoid requesting more information after the customer has clearly declined; offer the appropriate escalation instead.

6. **Escalate unconfirmed mailings when needed.**
   If the customer seeks to redeem or enforce a mailed offer that cannot be verified because they will not provide sufficient account-identifying/verification information, transfer to a human agent with reason `unconfirmed_external_communication`. Include a concise summary of:
   - the claimed promotion and terms;
   - the documented terms that can be stated generally;
   - that no account or offer was verified and no banking action was taken;
   - identifiers or verification the customer declined to provide.

   If the customer continues to demand an unavailable offer after it has been explained and the issue is no longer principally about validating the mailing, use `customer_demands_after_unavailable_offer_refusal` instead. Do not transfer merely to bypass verification or to authorize an unsupported promotion.

## Product reference: Business Bronze Rewards Card
Use `references/business_bronze_terms.md` when the inquiry concerns this product. The reference is general product documentation; it does not establish that any particular customer's flyer, account, or targeted offer is valid.

## Example executor outcome for an unverified mailing
When no verified account can be located and the customer will not provide the necessary identifier or identity information:

1. Do not call any card, transaction, or account-action tool.
2. Explain that the mailing cannot be validated or redeemed without locating and verifying the related profile/account.
3. State only the applicable documented general terms, if relevant.
4. Transfer with `unconfirmed_external_communication` and a factual summary. No statement credit, enrollment, fee waiver, or other account change is performed.

## Validation checklist
Before ending the interaction, confirm all of the following:

- No account-specific information was disclosed without verified identity and authority.
- No promotional credit, enrollment, fee change, or other banking action was performed based on an unconfirmed mailing.
- Any documented terms communicated match the product reference and are not represented as a targeted-offer validation.
- The account, offer code, card, eligibility, timing, qualifying spend, and fulfillment status were verified before any redemption action.
- If escalation occurred, the selected reason accurately matches the unresolved issue and the summary states that no action was taken.
