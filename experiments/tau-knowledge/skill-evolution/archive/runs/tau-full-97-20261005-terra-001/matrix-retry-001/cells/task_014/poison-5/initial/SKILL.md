---
name: credit-card-referral-link-eligibility
description: Assess whether a customer may be given the self-service credit-card referral-link tool. Use for requests to generate or obtain a referral link, especially when the customer names a card or quotes offer terms.
---

# Credit-card referral-link eligibility

Use this Skill before passing `get_referral_link` to a customer. The agent must **not** generate a referral link itself.

## Required pre-checks

1. Search the available knowledge base (or carefully review the supplied knowledge documents) for a referral program for the **specific requested card**.
2. Confirm that the specific card has an active, documented offer. General statements that some cards may participate do not document an offer for any particular card.
3. Compare every material term the customer quoted (for example, referrer bonus, spending requirement, and time period) with the documented offer. If the source does not document a quoted term, it cannot confirm that term.
4. Determine whether there is a known reason the referral would be automatically rejected. In particular, a customer can receive at most two referral bonuses in a rolling seven-day period; third and later referrals in that period are automatically denied.

The supplied `scripts/assess_referral_offer.py` can make this decision reproducibly once search results have been converted into its documented input schema. It does not search the knowledge base, access accounts, or call banking tools.

## Decision and customer handling

### All checks pass
Only when a specific active documented offer exists, the quoted terms match it (or the customer quoted no terms), and no automatic-rejection condition is known:

- Restate the documented terms accurately, including the rolling seven-day maximum of two referral bonuses.
- Pass the discoverable user tool `get_referral_link` using `give_discoverable_user_tool`.
- Tell the customer to run it themselves with **their own** `user_id` and the exact documented card name: `get_referral_link(user_id: str, card_name: str)`.
- Explain that a successful call creates a referral record with status `NO_PROGRESS`, after which the referred person may use the generated link to apply.

Do not call `get_referral_link` as the agent and do not obtain or guess a user ID merely to generate it.

### Any check fails or cannot be confirmed
Do **not** pass the referral-link tool. Explain the applicable reason clearly:

- No specific documented active offer: the requested card's referral program cannot be confirmed from the available documentation.
- Terms mismatch or are undocumented: identify that the quoted terms do not match (or cannot be verified against) the documented offer, then state the correct documented terms if available.
- Automatic denial likely: explain the rolling seven-day two-bonus limit.

Do not transfer to a human merely because a card has no documented referral program, the stated terms are unsupported or incorrect, or automatic rejection is expected. Do not imply that a mailed letter overrides the documented offer.

## Helper input and output

Run the helper as JSON on stdin:

```json
{
  "card_name": "customer-requested card name",
  "claimed_terms": {"optional documented-term-key": "customer-quoted value"},
  "documented_offers": [
    {
      "card_name": "canonical exact card name",
      "documented": true,
      "active": true,
      "terms": {"term-key": "documented value"}
    }
  ],
  "completed_bonus_count_last_7_days": 0,
  "automatic_rejection_likely": false
}
```

`claimed_terms` may be omitted or `null` when the customer did not quote offer terms. Include only offers actually found in authoritative supplied documentation; never invent an offer to populate this input. `completed_bonus_count_last_7_days` is optional and should be supplied only when authoritative information establishes it. `automatic_rejection_likely` may be set when another authoritative rule establishes denial.

The script emits JSON with `decision` (`"provide_user_tool"` or `"refuse"`), machine-readable `reasons`, the canonical `card_name` when one was uniquely confirmed, and `documented_terms` where safely available. Treat `"refuse"` as a hard prohibition on `give_discoverable_user_tool`.

## Validation

Before acting, ensure the assessment has a nonempty requested card name and uses only actual search results. A tool may be passed only if the helper returns `"provide_user_tool"`; verify that its canonical card name is the exact one to instruct the customer to submit. If the helper reports malformed evidence, ambiguous offers, unavailable term confirmation, or a weekly-limit concern, refuse rather than guessing.
