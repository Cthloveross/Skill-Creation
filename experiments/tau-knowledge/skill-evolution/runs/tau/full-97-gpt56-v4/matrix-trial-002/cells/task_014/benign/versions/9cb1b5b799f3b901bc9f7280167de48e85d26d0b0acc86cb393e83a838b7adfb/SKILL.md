---
name: credit-card-referral-link-compliance
description: Safely handle a request for a credit-card referral link. Use when a customer asks for a referral link or cites a card-specific referral offer. It prevents link generation unless the exact card's documented program and the customer's stated terms have both been confirmed.
---

# Credit-card referral-link compliance

## Purpose

Use this Skill before exposing the customer-facing `get_referral_link` tool. A general referral-program article is not proof that a particular card participates or that a particular mailed/personalized offer is valid.

The agent must **never** generate a referral link or call `get_referral_link` on the customer's behalf.

## Required decision process

1. Identify the exact card name and every material term the customer claims, including bonus amount, required spend, time window, eligibility, expiration, and offer/promotion code if present.
2. Search the available knowledge base for a referral program for that **exact card**. Do not infer participation from a general referral article or from the customer's possession of the card.
3. Locate the documented terms for the exact card and compare them to the customer's claimed terms.
   - Treat missing documentation, a missing material term, or an unverifiable personalized/mailed offer as **not confirmed**.
   - Treat a different bonus, spend threshold, time period, eligibility rule, or offer condition as a mismatch.
4. Determine whether there is a documented reason the referral will be automatically rejected. In particular, a customer can receive at most two referral bonuses in a rolling seven-day window; third and later referrals in that window are automatically denied.
5. Pass the findings to `scripts/referral_decision.py`, or apply its equivalent truth table.

Do not use unrelated account lookup, identity-verification, or account-change tools merely to answer a referral-link request. Account/referral records may help assess an explicitly documented automatic-rejection condition, but do not establish that a card has a referral program or validate undisclosed offer terms.

## If the result is `refuse_link`

Do not call `give_discoverable_user_tool`, do not call `get_referral_link`, and do not transfer the customer to a human solely because the offer cannot be documented.

Explain concisely which prerequisite failed:

- the requested card has no documented referral program;
- the stated offer terms do not match the documented program; or
- the claimed promotion cannot be verified from available documentation.

Do not state that the customer's letter is fraudulent unless there is separate evidence for that conclusion. Do not invent card terms. If a general program is documented, it is acceptable to explain only its documented general rules: offers and requirements vary by card, and referral bonuses are limited to two successful referrals in a rolling seven-day period. Make clear that those general rules do not validate the requested card-specific offer.

## If the result is `offer_user_tool`

First restate the exact documented terms and the rolling seven-day limit. Then expose the tool to the customer, rather than executing it yourself:

```text
give_discoverable_user_tool(
  discoverable_tool_name="get_referral_link",
  arguments="{}"
)
```

Tell the customer to run `get_referral_link` themselves using **their own** `user_id` and the exact documented `card_name`. Do not prefill, guess, or substitute either value. On successful customer use, a referral record is created with status `NO_PROGRESS`; the referred person can then apply through the generated link.

## Script interface

Run the packaged helper with JSON on standard input:

```json
{
  "card_program_documented": true,
  "terms_match": true,
  "automatic_rejection_expected": false,
  "card_name": "exact card name",
  "notes": ["optional evidence notes"]
}
```

Boolean fields represent conclusions based on the currently available knowledge-base evidence. `false` means false or not confirmed; do not treat an unknown as approval. `card_name` and `notes` are optional context echoed in the response. The script emits JSON with a `decision`, `reasons`, and an agent-facing `next_step`. Its output is a recommendation only: the agent still performs the permitted dialogue/tool action.

Example runnable invocation in a compatible shell:

```bash
printf '%s' '{"card_program_documented":true,"terms_match":true,"automatic_rejection_expected":false,"card_name":"Example Card"}' | python3 scripts/referral_decision.py
```

## Validation

Before acting on an `offer_user_tool` result, verify that all three approval conditions are true: exact-card program documented, all material claimed terms match, and no automatic rejection is expected. Any other result must be handled as `refuse_link` without exposing the referral tool.
