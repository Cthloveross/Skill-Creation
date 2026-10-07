---
name: credit-card-referral-link-eligibility
version: 1.0.0
description: Assess a request for a credit-card referral link against documented card-specific referral terms, and safely provide the self-service referral tool only when eligibility is documented and the customer's stated terms match.
---

# Credit-card referral link eligibility

Use this Skill when a customer asks for a credit-card referral link, especially when they cite a mailed offer, bonus amount, spending requirement, or other offer terms.

## Required pre-check

1. Identify the **exact card name** and the referral terms claimed by the customer.
2. Search the available knowledge base for a referral program specifically documented for that exact card.
3. Compare every material claimed term (for example, bonus amount, qualifying event, required spend, and timeframe) with the card-specific documented program.
4. Confirm the card has an active referral offer and that there is no documented reason the referral would be automatically rejected.
5. Remember that referral bonuses are capped at two successful bonuses in a rolling seven-day window across all card types. Referral records, when available, may be reviewed to explain a known cap issue.

Generic descriptions that referral offers vary by card, or generic statements that some cards participate, are **not** documentation of a program for a particular card. A card account record only confirms that the customer has a card; it does not establish a referral offer or its terms.

## Decision rules

Run `scripts/assess_referral_request.py` with the card-specific documentation findings and the customer's claimed terms. Interpret its result as follows:

- `provide_link_tool`: Tell the customer the documented terms and give them the discoverable user tool `get_referral_link`. Instruct them to run it themselves with their own `user_id` and the exact documented card name. Do not call or generate the link on their behalf. State that a successful call creates a `NO_PROGRESS` referral record.
- `decline_no_documented_program`: Explain that a referral program for that specific card is not documented or cannot be confirmed. Do not provide the referral-link tool and do not transfer the customer.
- `decline_terms_mismatch`: Explain that the customer-stated offer terms do not match the documented program. State the documented terms when available. Do not provide the referral-link tool and do not transfer the customer.
- `decline_auto_rejection`: Explain the documented automatic-rejection reason, including the rolling seven-day cap where applicable. Do not provide the referral-link tool and do not transfer the customer.
- `need_card_or_terms`: Ask only for the missing exact card name or claimed terms needed to perform the comparison. Do not provide the tool yet.

Do not infer card-specific benefits from a customer letter, account ownership, or a generic referral article. Do not transfer merely because an offer is unavailable or its terms are unconfirmed.

## Runtime helper

`scripts/assess_referral_request.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "card_name": "exact customer card name or empty string",
  "claimed_terms": {
    "bonus": "customer-stated bonus or null",
    "qualifying_requirement": "customer-stated condition or null",
    "timeframe": "customer-stated timeframe or null"
  },
  "documented_program_found": false,
  "documented_terms": {
    "bonus": null,
    "qualifying_requirement": null,
    "timeframe": null
  },
  "active_offer": false,
  "automatic_rejection_reason": null
}
```

Set `documented_program_found` only after locating documentation for the exact card. Set `active_offer` only when the documentation confirms an active offer. Use normalized, faithfully transcribed terms for both term objects; omit or set a value to `null` when unknown. If a documented automatic denial applies, provide its customer-safe explanation in `automatic_rejection_reason`.

Output includes `decision`, `give_referral_tool`, `transfer_to_human`, `reason`, and customer-facing response guidance. Validate that `give_referral_tool` is true only for `provide_link_tool`, and never call the banking referral function from this helper.

## Giving the tool after approval

Only for a `provide_link_tool` decision, call `give_discoverable_user_tool` with:

- `discoverable_tool_name`: `get_referral_link`
- `arguments`: an appropriate JSON string exposing the customer-supplied `user_id` and exact card name

Then clearly instruct the customer to execute that tool themselves. Reiterate the documented terms and the two-successful-bonus rolling seven-day limit. Do not use the tool or any substitute mechanism on the customer's behalf.

## Safe failure handling

If knowledge-base search cannot establish card-specific terms, treat the offer as undocumented rather than guessing. If customer identity information is absent, it is not a reason to expose a referral link; obtain only information needed by the normal support flow, while maintaining the required card-program and terms checks.