---
name: credit-card-referral-link-eligibility
description: Assess a request for a credit-card referral link before exposing the customer-run get_referral_link tool. Use when a customer names a card and may cite referral bonus terms.
---

# Credit Card Referral Link Eligibility

Use this Skill before offering a referral-link tool for a credit-card referral request. It enforces the prerequisites that the exact card has a documented active program, the customer's stated terms agree with that program, and there is no known automatic-denial condition.

## Required runtime information

Obtain from the knowledge base or task inputs:

1. The exact requested card name.
2. The active, card-specific documented referral offer, including all relevant terms.
3. The customer's stated terms, if any.
4. Whether the referrer already has two successful referral bonuses in the rolling seven-day window, when that information is available and relevant.

A general statement that some cards may have referral offers is not evidence that a named card has one. Do not infer an offer, amount, spend requirement, time period, or eligibility rule from a mailer alone.

## Evaluate

Run `scripts/assess_referral.py` with structured offer and claimed-term data. See the script's input schema below.

Interpret its decision as follows:

- `eligible_to_offer_tool`: Restate the documented terms, including the maximum of two successful referral bonuses in any rolling seven-day period. Give the customer—not the agent—the discoverable tool `get_referral_link`. Tell the customer to call it with their own `user_id` and the exact documented `card_name`. Do not call the referral tool, unlock an agent version, or generate a link on the customer's behalf.
- `no_documented_active_program`: Explain that no active card-specific referral program is documented for the requested card, so a referral link cannot be provided. Do not transfer solely for this reason and do not expose the tool.
- `terms_do_not_match`: Explain the discrepancy, state the documented terms when available, and do not expose the tool or transfer solely because the claimed terms are unavailable or incorrect.
- `term_confirmation_needed`: State the documented terms and ask the customer to confirm their understanding before considering the tool. Do not expose it yet.
- `automatic_denial_risk`: Explain that the referral would not qualify because the rolling seven-day maximum has already been reached. Do not expose the tool or transfer solely for this reason.
- `invalid_input`: Do not expose the tool. Resolve missing or malformed evidence from the knowledge base; if no card-specific evidence can be obtained, treat it as `no_documented_active_program`.

When eligible, expose the customer-run capability using `give_discoverable_user_tool` with `discoverable_tool_name` set to `get_referral_link` (and no agent-supplied user ID or card name). In the customer-facing instruction, explicitly say that they must supply their own ID and the exact card name. A successful customer call creates a referral record with status `NO_PROGRESS`; the referred person may then apply with the generated link.

## Script interface

`scripts/assess_referral.py` reads one JSON object from standard input and writes one JSON object to standard output. It makes no banking calls and never creates a link.

Input:

```json
{
  "requested_card_name": "string",
  "documented_offers": [
    {
      "card_name": "exact documented card name",
      "active": true,
      "terms": {"structured": "complete documented referral terms"}
    }
  ],
  "claimed_terms": {"structured": "terms stated by the customer"},
  "rolling_7_day_successful_referrals": 0
}
```

`claimed_terms` may be omitted or `null` when the customer has not confirmed any terms. Terms must use the same structured fields on both sides. The check intentionally requires the supplied claimed terms to match the full documented terms, preventing an unverified partial or altered offer from being approved. `rolling_7_day_successful_referrals` is optional; use a nonnegative integer when known.

Output includes `decision`, `provide_user_tool`, `exact_card_name`, `documented_terms`, and a stable `reasons` list. Validate that `provide_user_tool` is true only for `eligible_to_offer_tool`, and that an eligible result contains the exact documented card name and terms before using the result.

Example invocation (with values sourced at runtime, not hardcoded into the Skill):

```sh
python3 scripts/assess_referral.py <<'JSON'
{"requested_card_name":"<card>","documented_offers":[{"card_name":"<exact-card>","active":true,"terms":{"bonus":"<documented>"}}],"claimed_terms":{"bonus":"<documented>"},"rolling_7_day_successful_referrals":0}
JSON
```
