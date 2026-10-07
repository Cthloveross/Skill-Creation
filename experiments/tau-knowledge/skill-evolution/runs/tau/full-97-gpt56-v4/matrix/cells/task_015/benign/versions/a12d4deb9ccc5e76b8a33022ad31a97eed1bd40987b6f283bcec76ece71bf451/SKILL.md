---
name: credit-card-referral-link-policy
description: Evaluate a request for a credit-card referral link against documented card-specific offer terms, safely provide the user-run referral tool only when allowed, and explain refusals without transfer.
---

# Credit Card Referral Link Policy

Use this Skill when a customer asks to generate, receive, or share a credit-card referral link.

## Required pre-check

Before offering a link, search the available knowledge base for the **exact card name** and its referral program. Establish all of the following:

1. A referral program is documented for that specific card and is active.
2. The customer's stated bonus, qualifying activity, and time window match the documented terms.
3. There is no reason the new referral will be automatically rejected (including the rolling seven-day limit of two successful referral bonuses).

Use `scripts/evaluate_referral_request.py` after the documentation review if a deterministic decision record is useful. The script only recommends an outcome; it does not call banking tools or create a referral.

## If every pre-check passes

- Tell the customer the documented terms, including that the referred person must be approved and satisfy the applicable card-specific requirements.
- Remind them that no more than two successful referral bonuses can be earned in a rolling seven-day period; later referrals in that window are automatically denied.
- Give the customer—not the agent—the discoverable tool `get_referral_link` using `give_discoverable_user_tool`.
- Instruct the customer to run it with their own `user_id` and the exact card name. Do not obtain or use their ID to generate a link on their behalf.
- Explain that a successful call creates a referral record with status `NO_PROGRESS`; the invitee may then apply through the generated link.

## If any pre-check fails or cannot be confirmed

Do **not** give the referral-link tool, do not generate a link, and do not transfer to a human solely for this issue.

Briefly explain the specific reason:

- No card-specific program is documented: say that an active referral offer for that exact card cannot be confirmed.
- Stated terms conflict with documentation: say that the quoted terms cannot be confirmed and provide only the documented terms that are available.
- Automatic rejection is likely: explain the relevant limit or existing referral activity and do not advise an immediate retry.

Reiterate only supported general facts: eligibility and bonus requirements vary by card, the referred person must be approved and meet the applicable program requirements, and successful referral bonuses are limited to two in any rolling seven-day window. Do not invent an offer amount, spend threshold, or deadline.

## Referral-status guidance

When relevant, interpret records as follows: `NO_PROGRESS` means no application yet; `APPLIED` means awaiting a decision; `IN_PROGRESS` means the account was opened and requirements are still being met; `COMPLETE` means the bonus criteria were met; `REJECTED` means too many referral processes are active and should not be retried immediately; `ERROR` may be retried later or escalated internally if persistent.

## Runtime helper

Run the helper by sending JSON on stdin, for example:

```json
{
  "card_name": "Exact card name from the request",
  "documentation_status": "documented_matching",
  "customer_terms": {"bonus": "...", "qualification": "...", "time_window": "..."},
  "documented_terms": {"bonus": "...", "qualification": "...", "time_window": "..."},
  "automatic_rejection_likely": false
}
```

The output has `decision` (`provide_user_tool` or `decline`), `reasons`, and safe `response_points`. A `provide_user_tool` result still requires giving the tool to the user rather than invoking it as an agent. Inputs with unknown, absent, or mismatched documentation must result in `decline`.
