---
name: referral-offer-eligibility-and-link-routing
description: Assess a credit-card referral-link request against documented offer terms and the current date. Use this when a customer asks for a referral link, changes cards or offers during a conversation, quotes promotional terms that may be unavailable or expired, or asks to escalate an unavailable referral request.
---

# Referral Offer Eligibility and Link Routing

## Purpose
Determine whether a customer may be offered a referral-link tool, then give a concise, accurate response. This Skill is for referral eligibility and link routing only; it does not generate links or act as the customer.

## Required runtime inputs
Collect from the current conversation and approved knowledge sources:

- requested card and offer terms;
- whether that specific card has a documented referral program;
- documented bonus, qualifying spend, qualifying window, submission deadline, and applicable limits;
- current timestamp or date; and
- any documented reason a referral would be rejected.

Do not infer an offer from a different card, a general referral article, or a customer-provided letter alone. Recheck the documentation whenever the customer changes cards or terms.

## Decision procedure

1. Confirm that the requested card has a documented referral program and compare the customer's stated terms with it.
2. Evaluate date-based availability using the current date. A program accepting new referrals only through a stated date is unavailable after that date; treat the deadline as inclusive unless the source explicitly says otherwise.
3. Check for another documented disqualifier, including a known automatic-rejection condition.
4. Use `scripts/assess_referral_offer.py` for a reproducible assessment when structured facts are available. The script is advisory; the execution agent must treat the approved source documentation as authoritative.
5. Route based on the result:
   - **Eligible and documented:** reiterate the correct terms and provide the customer-facing `get_referral_link` tool through `give_discoverable_user_tool`. The customer must run it with their own `user_id` and the exact documented card name. Do not generate the link as the agent.
   - **Undocumented, terms mismatch, expired or closed, or likely automatic rejection:** do **not** provide a referral-link tool. Explain the specific documented reason, state the correct terms when available, and offer only non-link guidance such as checking the account for current offers.

## Mandatory no-transfer rule
For an undocumented referral offer, mismatched or unverified terms, an expired or closed program, or a referral likely to be automatically rejected, **never call `transfer_to_human_agents`**. This remains true if the customer repeats the request, asks for a supervisor or person, is dissatisfied, or explicitly requests escalation. The referral policy requires an explanation without transfer in these cases; a transfer-tool reason enum does not override that requirement.

Instead, give a concise final response that:

1. says the available documentation cannot confirm the offer or confirms that it is no longer eligible;
2. says that no referral link can be provided; and
3. suggests checking the customer's account or referral center for any current eligible offers when appropriate.

Do not perform identity lookup, verification, referral lookup, or other account actions merely to communicate this unavailable-offer outcome.

## Response content
For an unavailable offer, plainly say that a referral link cannot be provided because the offer is undocumented, does not match the documented terms, is no longer accepting new referrals, or has another applicable documented rejection condition. Where terms are documented, distinguish the conditions for earning a completed-referral reward from the deadline for submitting a new referral. Do not imply that satisfying qualifying spend after an intake deadline creates a new eligible referral.

For an available offer, remind the customer that invitations should be sent only to contacts who consent, self-referrals are prohibited, and applicable program limits remain in force. Include only limits supported by the applicable documentation.

## Tool handoff for an eligible request
Only after every eligibility check passes, call:

- `give_discoverable_user_tool` with `discoverable_tool_name` set to `get_referral_link`.

Tell the customer to call the provided tool using their own user ID and the exact documented card name. Do not call it, unlock an agent-side equivalent, or generate a link on the customer's behalf.

## Script interface
`scripts/assess_referral_offer.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "current_date": "YYYY-MM-DD or timestamp",
  "documented": true,
  "terms_match": true,
  "submission_deadline": "YYYY-MM-DD or null",
  "automatic_rejection_reason": "string or null"
}
```

Output contains `decision` (`offer_link_tool` or `do_not_offer_link_tool`), `must_not_transfer`, `reasons`, and normalized date fields. Missing or invalid required evidence is handled conservatively as `do_not_offer_link_tool` with `must_not_transfer: true`.

Example runnable invocation with runtime-supplied values:

```sh
printf '%s' '{"current_date":"2025-01-01","documented":true,"terms_match":true,"submission_deadline":"2025-12-31","automatic_rejection_reason":null}' | python3 scripts/assess_referral_offer.py
```

Validate that `decision` is `offer_link_tool` only if `documented` and `terms_match` are true, no rejection reason is present, and the current date is on or before any supplied deadline. For every `do_not_offer_link_tool` result, do not offer a link and do not transfer the customer.
