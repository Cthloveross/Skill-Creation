---
name: credit-card-referral-link-triage
description: Safely handles customer requests for a credit-card referral link. Use when a customer names a card or referral offer and asks how to obtain or generate a link.
---

# Credit Card Referral Link Triage

Use this workflow before offering a customer the `get_referral_link` discoverable tool. A referral-link request is eligibility-sensitive: do not infer that a card participates merely because the customer reports receiving an offer.

## Inputs

Read the current conversation and the authorized knowledge-base material supplied for the task. Capture:

- the exact card name requested;
- every customer-stated bonus amount, spending threshold, time period, and other offer term;
- whether the customer is asking for instructions, a link, or status help; and
- any available verified customer identity or card ownership information.

## Required decision process

1. Search the authorized knowledge material for a referral program specifically documented for the exact requested card.
2. Compare the customer's stated terms against the documented program terms. Treat an offer as unverified if the documentation gives only general referral information, says that card-specific terms vary, or does not state the requested card's active offer and matching terms.
3. Do **not** provide a referral-link tool if any of these applies:
   - no referral program is documented for that specific card;
   - the claimed terms do not match documented terms;
   - the claimed mailed or external offer cannot be confirmed from the authorized documentation; or
   - available referral information shows the referral would be automatically denied, including the rolling seven-day referral-bonus cap.
4. In a refusal, clearly state the applicable reason, correct any inaccurate general rule that is documented, and suggest checking the official card offer or customer service. Do not transfer to a human solely because the card offer is undocumented, terms conflict, or a referral would be automatically rejected. Do not call `give_discoverable_user_tool`.
5. Only if the exact card's active program and relevant customer-stated terms are documented and consistent, perform the required banking control checks before an action: verify customer identity, authority, account ownership, product eligibility, applicable limits, and any confirmation requirements. Check any available referral history when it is necessary to determine whether the rolling cap would cause automatic denial.
6. If all checks pass, explain the documented terms and the rolling seven-day limit. Then call `give_discoverable_user_tool` with:
   - `discoverable_tool_name`: `get_referral_link`
   - `arguments`: `{}`

   Tell the customer to run the provided tool themselves using their own `user_id` and the exact documented card name. Do not generate a link on the customer's behalf. Explain that a successful call creates a referral record with status `NO_PROGRESS`, after which the referred person may use the generated link to apply.

## Response rules

- Never invent card-specific rewards, spending requirements, approval conditions, or dates.
- General documentation that referral programs may exist is not proof that a particular card has one.
- State that referral bonuses are limited to at most two in any rolling seven-day window when that rule is documented. The third and later referrals in that period are automatically denied.
- Do not request or expose sensitive identity data unless it is necessary for the permitted workflow and the customer can provide it through the normal verified process.
- If the request lacks an exact card name, ask for it rather than offering the tool.
- If identity or eligibility cannot be verified for an otherwise documented offer, explain that verification is needed before proceeding; do not provide the tool until it is complete.

## Tool-use contract

This is a conversational workflow rather than a local computation. The executor uses only the runtime's normal banking and discoverable-tool interfaces. `give_discoverable_user_tool` makes the action available to the customer; it does not execute the referral action for them. Do not substitute scripts, guessed URLs, or agent-side calls for the customer-operated referral tool.

## Validation checklist

Before finalizing the response, confirm all of the following:

- The named card has a specifically documented active referral program.
- Every material customer-claimed term matches the documentation.
- Required identity, authority, ownership, eligibility, limit, and confirmation checks are satisfied before any action.
- The rolling seven-day cap would not automatically deny the referral.
- The referral tool is offered only on a pass; otherwise it is not offered and no human transfer is made for the unavailable/incorrect offer alone.
- Any successful-path instructions require the customer, not the agent, to run the tool with their own user ID and exact card name.
