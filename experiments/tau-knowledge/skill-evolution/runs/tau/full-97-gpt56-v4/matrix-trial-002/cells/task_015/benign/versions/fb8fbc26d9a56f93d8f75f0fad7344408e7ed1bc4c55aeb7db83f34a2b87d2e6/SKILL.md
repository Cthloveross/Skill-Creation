---
name: safe-credit-card-referral-link-guidance
description: Handle requests for a credit-card referral link. Use when a customer wants to refer someone, cites referral bonus terms, or asks how to generate a referral link. Ensures the card's active documented offer and the customer's stated terms are verified before offering the customer-operated referral-link tool.
---

# Safe Credit Card Referral Link Guidance

## Purpose

Referral offers are card-specific. Do not infer that an account holding, a mailing, a generic referral article, or a prior referral proves that a particular card currently has the claimed offer.

## Required decision process

1. Identify the **exact card name** and the terms the customer believes apply, including bonus, qualifying activity, timing, offer/campaign code, and expiration when available.
2. Search the available knowledge base for a documented, active referral program for that exact card. Check its eligibility and bonus requirements.
3. Compare the customer's stated terms with the documented terms.
4. If available and relevant, review referral history to determine whether a new referral has a known automatic-denial reason. The cap is two referral bonuses in any rolling seven-day window, across card types. Do not treat a lack of referral history as proof of an active offer.
5. Use `scripts/referral_decision.py` to record the outcome consistently. It is a decision aid; it neither searches the knowledge base nor performs any banking action.

## When all prerequisites pass

Only when the exact card has a documented active referral program, the customer's stated terms match it, and there is no reason to expect automatic rejection:

- Restate the documented terms accurately, including the rolling seven-day cap.
- Use `give_discoverable_user_tool` to provide `get_referral_link` to the customer. Do **not** call `get_referral_link` yourself.
- Tell the customer to call it themselves with their own `user_id` and the exact documented `card_name`. A successful call creates a referral record with status `NO_PROGRESS`; the referred person can then apply with the generated link.
- Do not substitute a shortened, guessed, or account-display variant of the card name.

## When a prerequisite fails or cannot be established

Do not provide the referral-link tool and do not generate a link. This includes when:

- no documented active program exists for the requested card;
- the stated terms conflict with documented terms;
- the available documentation is generic and does not establish the requested card's program or terms;
- a particular claimed mailed/external offer cannot be verified from available terms or offer details; or
- there is a reason the referral will automatically be denied.

Clearly explain the specific verification gap or discrepancy. State that the link cannot be provided for the claimed offer until an active documented offer and its terms can be confirmed. Do **not** transfer to a human merely because an offer is unavailable, unverified, or mismatched.

If, after that explanation, the customer explicitly asks to speak with a human because the offer was unavailable or could not be verified, transfer using `transfer_to_human_agents` with reason `customer_demands_after_unavailable_offer_refusal`. Summarize the exact card/terms requested and that no link tool was provided or generated. This escalation does not change the referral-link prerequisites.

## Script interface

Run:

```bash
python3 scripts/referral_decision.py <<'JSON'
{"card_name":"<exact requested card>","program_documented":true,"terms_match":true,"automatic_rejection_reason":null}
JSON
```

Input is a JSON object:

- `card_name` (string): exact card requested; used only in the decision output.
- `program_documented` (boolean): true only after confirming an active card-specific documented program.
- `terms_match` (boolean): true only when the customer terms match the documented offer. Set false when terms are absent or cannot be verified.
- `automatic_rejection_reason` (string or null): a specific known automatic-denial reason, if any.

The script emits JSON with `eligible_to_offer_user_tool`, `reason_code`, and `next_step`. Validate that `eligible_to_offer_user_tool` is true before providing the user tool. A false result requires a refusal/explanation, not escalation.

## Customer-facing response checklist

- Be explicit about what is and is not verified; never claim a card or offer is eligible without documentation.
- If refusing, avoid suggesting that an agent can bypass the rule or create a link.
- If the customer then expressly requests a human after the unavailable-offer refusal, transfer with reason `customer_demands_after_unavailable_offer_refusal` and accurately summarize the verification gap.
- If approved, say the customer must run the tool themselves and include the exact tool name and required parameters.
- Always remind customers that no more than two referral bonuses can be received in a rolling seven-day period across all card types; further referrals in that window are automatically denied.
