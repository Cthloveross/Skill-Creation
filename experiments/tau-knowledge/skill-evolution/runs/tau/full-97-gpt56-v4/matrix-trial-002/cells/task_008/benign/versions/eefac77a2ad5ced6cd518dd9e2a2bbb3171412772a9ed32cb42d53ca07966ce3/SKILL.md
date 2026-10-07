---
name: unverified-credit-card-promotion
version: 1.0.0
description: Handle a request to redeem a mailed or external credit-card promotion when the offer cannot be matched to documented terms or authenticated. Use this for pre-application customers as well as account holders; do not create, alter, or credit an account based on an unverified offer.
---

# Unverified Credit-Card Promotion

## Purpose
Resolve promotion questions using only the documented offer terms and the information the customer can provide. A flyer, verbal assertion, or incomplete transcription is not sufficient to create a special offer, apply a statement credit, or promise approval.

## Required intake
1. Determine whether the customer already has an account. If they do, locate it using an appropriate identifier and follow identity-verification requirements before disclosing account-specific information or making account changes.
2. Obtain the promotion's card/product name, offer or invitation code, expiry/opening date, application URL or instructions, and all available terms. Ask for a complete image or exact transcription when possible.
3. Compare the claimed amount, spend threshold, qualifying period, product type, eligibility, and offer dates against the documented offers.
4. Record only facts the customer supplied and tool results. Do not infer that a product, code, or marketing offer exists from a claimed benefit alone.

## Decision rules
- Honor or describe a specific promotion only when its product and terms can be matched to documented terms and the customer can meet those terms. Do not change a documented bonus amount or qualification period.
- A similar promotion is not a match when any material term differs, including the credit amount, required spend, qualifying period, card type, or offer window.
- Do not substitute a business-card offer for a customer seeking a personal card or who states they do not operate a business. Do not tell the customer they are approved or eligible unless the documented application process makes that determination.
- If the flyer lacks identifying details and cannot be authenticated, explain that the requested offer cannot be honored or applied based on the available information. Do not fabricate an application path, offer code, expiration date, or exception.
- A customer without an existing account cannot receive a statement credit merely by requesting it; any credit is contingent on opening the applicable account and satisfying its documented qualification terms.

## Use of the supplied offer evidence
When the available evidence is the Business Bronze and Silver Rewards material:
- The documented Business Bronze promotion is a **$500 statement credit** after **$10,000 in net purchases posted within the first two months**, for accounts opened from **2025-10-01 through 2026-03-31**. It is a business-card offer; returns/credits reduce qualifying purchases.
- The documented Silver Rewards promotion is a **$500 statement credit** after **$2,000 in posted net purchases in the first month**, for accounts opened from **2025-01-01 through 2025-06-30**.
- Neither description supports a $1,000 credit for $10,000 in two months. Do not represent either documented offer as that claimed offer.

Check the current date when assessing an offer window. State dates and terms precisely, but do not promise an offer remains available beyond the terms supplied.

## Customer response pattern
Use a concise, empathetic response:
1. Acknowledge that the customer expected the stated promotion.
2. State that the offer cannot be verified or honored with the missing product/offer identification and because its material terms do not match the documented offers.
3. If useful, accurately distinguish the documented offers without presenting either as a replacement or guarantee.
4. State the safe next step: provide an authentic offer code, product name, full terms, or a clear copy of the communication for review. If the customer cannot provide these and continues to demand honoring the offer, transfer rather than speculate or make an exception.

Do not request unnecessary sensitive data from a person who has no account. Do not claim the institution sent the flyer, accuse the customer of fraud, or say the flyer is fake; the correct finding is that it is unconfirmed.

## Escalation
If the customer continues to demand that an unverified or unavailable external promotion be honored after the explanation, call `transfer_to_human_agents` with:
- `reason`: `unconfirmed_external_communication`
- `summary`: a factual summary containing the claimed terms, missing identifiers, account lookup result if performed, the documented mismatch, and that no credit, account change, or offer promise was made.

Use `customer_demands_after_unavailable_offer_refusal` only when the communication itself has been sufficiently identified but the documented offer is definitively unavailable. For an unidentified flyer or unverified mailing, use `unconfirmed_external_communication`.

## Completion checklist
Before ending or transferring, confirm:
- No unverified offer was redeemed, promised, or manually applied.
- Any comparison uses the exact documented amount, spend, period, product type, and dates.
- No customer account action was taken without the required identification and verification.
- The response gives the customer a truthful explanation and an evidence-based next step.
