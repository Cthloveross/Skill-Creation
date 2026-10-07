---
name: unverified-promotion-escalation
description: Handle a customer attempting to redeem a mailed, emailed, or printed promotion whose issuer, product, code, or terms cannot be verified against available promotion knowledge. Use this Skill to explain the verified terms without inventing eligibility or honoring the claim, then transfer to a human specialist with the highest-priority applicable reason.
---

# Unverified Promotion Escalation

Use this Skill when a customer presents a specific external promotion (for example, a flyer, letter, email, invitation, or advertisement) and asks to redeem or honor it.

## Inputs

At runtime, obtain:

- The customer's claimed promotional terms and requested outcome.
- Any identifying details on the external item: issuer, product/card name, promotion or invitation code, URL, expiration date, and relevant fine print.
- The available promotion knowledge and the result of comparing the claim with it.
- Whether the customer has an account or application, if needed for the request. Do not request or look up identity information unless it is necessary for an authorized action.

The optional `scripts/assess_promotion.py` helper accepts these findings as JSON and returns a deterministic escalation recommendation. It does not perform bank actions.

## Procedure

1. Identify the claimed terms exactly, including the reward amount, required spend, qualification window, and the asserted source (such as a mailed flyer).
2. Ask for enough identifying information to locate the promotion: product/card name, issuer or logo, offer/invitation code, URL, expiration date, and readable heading/fine print. If applicable, establish whether the customer has an account or pending application.
3. Compare the claim only with available, applicable knowledge. Do not treat a superficially similar offer as validation when material terms differ (for example, a different statement-credit amount) or the item cannot be tied to a product or issuer.
4. If the external promotion cannot be verified, tell the customer succinctly that you cannot confirm or honor that particular offer through the available information. You may state verified offer terms only as a comparison and must clearly distinguish them from the customer's claimed offer. Do not promise that a credit, application approval, or exception will be granted.
5. Transfer to a human agent using the highest applicable reason code:
   - Use `unconfirmed_external_communication` when the customer claims a specific external promotion, program, or offer and it cannot be verified after the available knowledge has been checked. This Tier 2 reason takes priority over generic requests or frustration.
   - Use a Tier 1 reason instead if a documented Tier 1 scenario independently applies (for example, fraud/security, legal matter, or a technical system error).
   - Do not use `customer_demands_after_unavailable_offer_refusal` unless the customer was told that the offer is unavailable, persisted multiple times, and then demanded a human.
6. Call `transfer_to_human_agents` with a factual `summary`. Include the claimed terms, identifying details that were unavailable or supplied, the comparison/check performed, that the claim could not be verified, and the customer’s requested resolution. Do not include unsupported conclusions or sensitive data that was not needed.

## Output and action

The required operational outcome for an unverified external promotion is a `transfer_to_human_agents` call with reason `unconfirmed_external_communication` and a concise factual summary. Follow the transfer with any required user-facing confirmation according to the host conversation workflow.

Example tool payload shape (replace all values with runtime facts):

```json
{
  "reason": "unconfirmed_external_communication",
  "summary": "Customer seeks to redeem an external promotion claiming [claimed terms]. The item lacks or did not provide [identifiers]. Available promotion information was checked and does not verify this claimed offer [comparison]. Customer requests that the offer be honored; specialist review is needed."
}
```

## Validation

Before transferring, verify that:

- The claim concerns a specific external communication, not merely a general request for current offers.
- Available knowledge was checked and does not substantiate the claimed offer, or identifying information is insufficient to verify it.
- No higher-priority Tier 1 transfer reason applies.
- The transfer summary describes facts and the attempted verification without guaranteeing an outcome.

Run the helper when useful:

```text
python scripts/assess_promotion.py <<'JSON'
{"external_promotion_claimed":true,"knowledge_checked":true,"promotion_verified":false,"tier1_reason":null,"claimed_terms":"...","missing_identifiers":["product name"],"comparison":"...","customer_request":"..."}
JSON
```

A valid helper result has `action` equal to `transfer_to_human_agents` and a permitted `reason`; copy its generated `summary` only after confirming it accurately reflects the live conversation.
