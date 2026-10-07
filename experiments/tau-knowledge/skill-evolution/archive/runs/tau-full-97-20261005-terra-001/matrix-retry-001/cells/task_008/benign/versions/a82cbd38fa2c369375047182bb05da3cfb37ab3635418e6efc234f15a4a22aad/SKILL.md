---
name: unverifiable-promotional-flyer-routing
description: Handle a customer claim based on a mailed, emailed, or printed promotion that cannot be matched to documented offer terms. Use this Skill to select the correct human-transfer reason, avoid unsupported promotional credits, and prepare a factual summary for review.
---

# Unverifiable Promotional Flyer Routing

Use this Skill when a customer cites a specific external promotion but available offer documentation does not verify it. This applies whether the customer is an applicant or an existing account holder.

## Required checks

1. Record the claimed benefit, spending requirement, timeframe, product/card name, and any offer identifier, expiration date, application URL, QR code, mailing label, or fine print available from the customer.
2. Search available offer documentation for the exact offer and its material terms. Do not treat a partly similar offer as confirmation.
3. Check for an eligible account only if account-specific servicing is necessary and identity/account lookup is possible. Do not ask for or infer an account ID when the customer says they do not have an account.
4. Never apply a promotional statement credit solely from an unverified flyer. A statement-credit action requires a real eligible credit-card account and confirmed entitlement.
5. If the promotion remains unverified after the search, explain that it cannot be confirmed from available terms and route it to a human agent for review. This remains the correct route if the customer repeats the claim or alleges false advertising.

## Transfer selection

Use `scripts/route_promo_claim.py` as a decision aid after the knowledge-base search. For an unverified external flyer, select:

- `unconfirmed_external_communication`

This Tier 2 knowledge/capability route takes priority over lower-tier disposition reasons such as frustration or a generic request for a human. Do **not** select `legal_or_regulatory_matter` merely because a customer alleges false advertising; that code is for actual legal or compliance matters such as subpoenas, court orders, or garnishments.

The Tier 1 reason `customer_demands_after_unavailable_offer_refusal` applies only when the offer is known not to exist in the system, the customer was told it is unavailable, the customer persisted multiple times, and then demands a human. A flyer that cannot be verified is instead `unconfirmed_external_communication`.

## Current evidence interpretation

The packaged evidence establishes that the documented $10,000-in-two-month offer is a $500 statement credit associated with a Business Bronze card, not a $1,000 personal-card offer. It therefore does not verify a claimed $1,000 personal-card flyer with those terms. See `references/frozen_evidence.md`.

For the supplied interaction, the customer reports no account, no product name or offer code, no identifying flyer details, wants a personal card, and continues to demand that the $1,000 flyer be honored after searches and clarification. Do not use an account-credit tool. Transfer using `unconfirmed_external_communication` and a factual summary.

## Executor procedure

1. Optionally run the script with facts established in the conversation. It emits a transfer recommendation and concise safe summary.
2. Before escalation, clearly tell the customer that the claimed promotion cannot be verified from available terms. If relevant, distinguish the documented $500 Business Bronze offer from the claimed $1,000 personal flyer; never present the former as the customer's offer.
3. Call `transfer_to_human_agents` with the script's `reason` and `summary`, or an equivalently factual summary. Include the claimed promotion, unavailable identifiers, lack of verification, account status when known, and requested review. Do not invent identifiers or sensitive information.
4. Treat the human transfer as complete only after its joined tool result reports success. If the conversation remains active after success, confirm that a human agent will review the promotion. A successful joined result that clearly says a human agent will assist is itself valid customer-facing confirmation if the interaction ends at that result.
5. Do not unlock or call `apply_statement_credit_8472` unless entitlement is independently confirmed and all required account information exists. This Skill does not establish either condition.

Suggested customer-facing wording:

> I’m unable to verify the $[claimed amount] promotion from the documented offer terms with the details available. I can have a human agent review the mailed promotion; I can’t apply or promise the credit before that review.

## Script interface

Run:

```text
python3 scripts/route_promo_claim.py <<'JSON'
{"external_promotion_claimed":true,"promotion_verified_in_kb":false,"customer_has_account":false,"customer_requested_or_demands_review":true,"claim_description":"<brief factual description>","missing_identifiers":["product name","offer code"]}
JSON
```

Input is one JSON object:

- `external_promotion_claimed` (boolean, required): the customer relies on a flyer, email, letter, or similar external communication.
- `promotion_verified_in_kb` (boolean, required): `true` only for an exact verified match.
- `customer_has_account` (boolean, required): whether an account is known to exist.
- `customer_requested_or_demands_review` (boolean, required): whether the customer asks, demands, or needs human review after the result.
- `claim_description` (string, required): concise factual description without personal data.
- `missing_identifiers` (array of strings, optional): unavailable details that would identify the offer.
- `specific_operational_reason` (string, optional): an applicable Tier 1 reason code. It overrides the external-communication route only when genuinely applicable.

The script writes one JSON object with `action`, `reason`, `summary`, and `validation`. Validate that `action` is `transfer`, `reason` is an enum accepted by `transfer_to_human_agents`, and the summary accurately reflects the actual conversation before making the transfer.

## Failure handling

- If the customer later provides a code, complete terms, or an exact offer identifier, search it before deciding the promotion is unverified.
- If search has not been performed, do not state that the offer is unavailable; collect identifiers or search first.
- If a Tier 1 event is present, use that specific Tier 1 reason instead.
- If no external communication is claimed and the customer merely wants a human, use the applicable disposition reason rather than this Skill's transfer reason.
- If the transfer tool reports an error, do not claim that the transfer succeeded. Explain the limitation only as supported by the result and follow available escalation procedures.
