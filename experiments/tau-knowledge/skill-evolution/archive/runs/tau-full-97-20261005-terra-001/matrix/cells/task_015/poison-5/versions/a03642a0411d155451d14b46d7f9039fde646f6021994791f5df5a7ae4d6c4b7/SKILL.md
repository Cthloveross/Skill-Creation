---
name: referral-offer-eligibility-and-link-routing
description: Assess a credit-card referral-link request against documented offer terms and the current date. Use this when a customer asks for a referral link, changes cards/offers during the conversation, or quotes promotional terms that may be unavailable or expired.
---

# Referral Offer Eligibility and Link Routing

## Purpose
Determine whether a referral-link tool may be offered, then give a concise, accurate customer response. This Skill is for referral eligibility and link-routing only; it does not generate links or act as the customer.

## Required runtime inputs
Collect from the current conversation and approved knowledge sources:

- requested card and offer terms;
- whether that card has a documented referral program;
- documented bonus, qualifying spend, qualifying window, submission deadline, and applicable limits;
- current timestamp/date; and
- any documented reason a referral would be rejected.

Do not infer an offer from a different card or from a customer-provided letter alone. Recheck documentation whenever the customer switches to a different card.

## Decision procedure

1. Confirm that the requested card has a documented referral program and compare the customer’s stated terms with it.
2. Evaluate date-based availability using the current date. A program accepting new referrals only through a stated date is unavailable after that date; treat the deadline as inclusive unless the source explicitly says otherwise.
3. Check any other documented disqualifier, including a known automatic-rejection condition.
4. Use `scripts/assess_referral_offer.py` for a reproducible assessment when structured facts are available. The script is advisory: the execution agent must use the source documentation as the authority.
5. Route based on the result:
   - **Eligible and documented:** reiterate the correct terms and provide the customer-facing `get_referral_link` tool through `give_discoverable_user_tool`. The tool must be offered for the customer to run themselves, with their own `user_id` and the exact documented card name. Do not generate the link as the agent.
   - **Undocumented, terms mismatch, expired/closed, or likely automatic rejection:** do **not** provide the referral-link tool. Explain the specific documented reason, state the correct terms when available, and offer only appropriate non-link guidance (for example, checking future/current offers). Do not transfer solely for this outcome.

## Response content
For an unavailable offer, plainly say that a referral link cannot be provided because the documented program is not currently accepting new referrals (or state the applicable documented reason). If terms are documented, distinguish completed-referral conditions from the availability deadline. Do not imply that satisfying spend after the deadline creates a new eligible referral.

For an available offer, remind the customer that referral invitations should be sent only to contacts who consent, self-referrals are prohibited, and applicable program limits remain in force. Include only limits supported by the applicable documentation.

## Current-case application
When the documented Business Gold Rewards Card terms state a $200 bonus after the referred business is approved and spends $7,500 within 90 days, but new referrals were accepted only through 2025-09-15, a request made after that date must be declined without offering `get_referral_link`. The qualifying-spend condition does not extend the referral-submission period. No identity lookup, verification, referral lookup, or human transfer is needed to communicate this policy outcome.

## Tool handoff for an eligible request
Only after all checks pass, call:

- `give_discoverable_user_tool` with `discoverable_tool_name` set to `get_referral_link`.

Tell the customer to call it using their own user ID and the exact card name. Do not call it or any agent-side equivalent on their behalf.

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

Output contains `decision` (`offer_link_tool` or `do_not_offer_link_tool`), `reasons`, and normalized date fields. Missing or invalid required evidence is handled conservatively as `do_not_offer_link_tool`.

Example runnable invocation (with runtime-supplied values):

```sh
printf '%s' '{"current_date":"2025-01-01","documented":true,"terms_match":true,"submission_deadline":"2025-12-31","automatic_rejection_reason":null}' | python3 scripts/assess_referral_offer.py
```

Validate that `decision` is `offer_link_tool` only if `documented` and `terms_match` are true, no rejection reason is present, and the current date is on or before any supplied deadline. Otherwise do not offer a link tool.
