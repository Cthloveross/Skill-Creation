---
name: credit-card-promotion-comparison
description: Provide an evidence-based, date-current comparison of credit-card sign-up bonuses, statement credits, cash back, points, annual fees, fee waivers, and introductory APR offers. Use when the task supplies promotion documents and a current-time observation; informational only, not for applying for or servicing an account.
---

# Credit Card Promotion Comparison

Use this skill to answer a customer's question about currently available credit-card promotions directly and accurately from the promotion records supplied with the task.

## Scope and safety

This is an informational workflow. Do not collect identity information, look up a customer, estimate approval odds, request an invitation, submit an application, or perform any account action. Do not say a customer qualifies or will be approved unless all applicable conditions have actually been independently established.

A missing customer profile does **not** make supplied public promotion records unavailable. Describe documented eligibility limits conditionally (for example, “if you are invited” or “for qualifying new customers”).

If the request changes into a banking action, preserve this prerequisite verbatim in the resulting banking procedure and use the execution agent's normal banking tools:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs and evidence handling

Read the current task's supplied promotion and product documents plus a successful read-only current-time observation. Treat source documents as the authoritative evidence for the response; do not require the customer to repeat facts already present in those documents.

For each potentially relevant promotion, capture:

| Field | What to capture |
| --- | --- |
| Product | Card name and consumer or business context |
| Benefit | Bonus amount, unit, and payout form (statement credit, cash back, points, fee waiver, or APR) |
| Window | Explicit start/end dates and the event that must occur during that window |
| Qualification | Invitation, new-customer, spend, eligible or net-purchase, timing, good-standing, and posting conditions |
| Cost | Annual fee, any promotion-based waiver, and conditions under which the normal fee applies |
| Value basis | Any explicitly documented point redemption rate |

Use a specific offer document to establish a campaign window and its conditions. A product/application document may corroborate an offer or fee but must not be used to extend a dated campaign beyond its stated window.

## Required method

1. **Establish the as-of date.** Extract the local `YYYY-MM-DD` date from the successful supplied time observation. Promotion endpoints are inclusive. If no reliable time observation is supplied, explain that current status cannot be determined from the supplied material.
2. **Classify dates.** Mark an offer active only if its explicit window includes the as-of date. Keep expired and upcoming offers out of the list of currently available promotions. If a record has no applicable explicit window, say its current status is unknown rather than assuming it is active.
3. **Separate promotion types.** For a sign-up-bonus request, lead with active statement-credit, cash-back, cash, and points bonuses. Mention active 0% APR or standalone fee-waiver promotions separately, not as sign-up bonuses.
4. **Compare value accurately.** Rank direct USD statement-credit/cash bonuses by their documented dollar amount. Convert points only when the records explicitly state a redemption rate. Retain the points name and amount even when showing an approximate documented cash-equivalent; never describe points as dollars merely because their numeric count is large.
5. **Account for attainability and cost.** For every listed bonus, state material invitation-only or new-customer limits, spend threshold, qualifying period, purchase exclusions, good-standing terms, and documented annual fee or waiver. A high face-value invitation offer is not generally available.
6. **Give a usable conclusion.** Identify the largest/highest documented headline sign-up bonus, then explicitly contrast it with the more accessible qualifying alternative(s). If an active business-card promotion exists, label it as a business-card alternative and do not imply it is a consumer-card offer.

## Mandatory response coverage

When source records establish active sign-up bonuses, the response must name the cards and provide the actual documented terms. It must not merely say that records cannot be confirmed, that more details are needed, or offer a generic explanation of how bonuses work.

For each active sign-up offer discussed, include:

- card name and whether it is consumer or business when applicable;
- bonus amount and its form;
- active status as of the observed date or its applicable current window;
- spending threshold and qualification period;
- invitation-only or new-customer restriction, when documented;
- eligible/net-purchase, return/credit, and good-standing conditions where documented; and
- annual fee and fee-waiver result, if documented and relevant to the customer's priorities.

For the highest face-value active bonus, explicitly use a comparison term such as **largest**, **highest**, **best by documented bonus value**, or **top**. State both why it has that headline value and why its eligibility or spend requirement may make it impractical. Include a current non-invitation alternative when evidence establishes one.

When comparing a business option, make the context clear, for example: “For a qualifying business applicant, the business-card alternative is …; it is separate from the consumer-card choices.” Do not assume that a customer has a business.

A complete response normally follows this form:

```text
As of [observed date], the largest active headline sign-up bonus is [card]:
[benefit]. It is active [window] and requires [invitation/new-customer status],
[eligible/net spend] in [period], and [good-standing/material terms]. [State
annual-fee/waiver result if documented.]

Other active sign-up options:
- [consumer card]: [points/cash benefit] after [spend] in [period], for
  [eligibility group]. [Give point value only if documented.] [State fee.]
- [business card, only if applicable]: [benefit] after [net spend] in [period].
  This is a business-card option; [state fee].

Bottom line: [leader] has the highest stated value, but [invitation and/or high
short-term spend reason]. [accessible consumer alternative] is more practical
for a qualifying new customer. If the customer has a qualifying business,
[business alternative] may suit a lowest-annual-fee priority.
```

Do not claim that an invitation will be sent, that an application will be approved, or that a customer meets conditions that have not been verified.

## Structured-data helpers

The helpers are optional deterministic checks after the executor transcribes the source evidence into structured JSON. They make no network calls and never access customer information. Scripts receive one JSON object on stdin and emit one JSON object on stdout.

### `scripts/analyze_offers.py`

Input schema:

- `as_of`: required string beginning with `YYYY-MM-DD`;
- `offers`: required array of objects containing `card`, `offer_type`, `window_start`, `window_end`, and `reward`;
- `offer_type`: use `signup_bonus` for a sign-up bonus; other values are retained as non-sign-up promotions;
- `reward`: object with `kind` (`statement_credit`, `cash_back`, `cash`, `points`, or `other`), `amount`, `currency`, and optional documented `redemption_value_per_point`;
- optional `qualification`, `annual_fee`, `supplemental_benefits`, `product_scope`, `details`, and `fulfillment` fields.

Output schema includes `ranked_active_signup_bonuses`, `active_non_signup_offers`, `inactive_or_unknown_offers`, `warnings`, and `errors`. Points lacking a documented conversion are retained but not ranked against USD.

### `scripts/compose_offer_response.py`

Accepts the `analyze_offers.py` input schema plus optional `product_scope` (`consumer`, `business`, or `all`) and `include_non_signup` (boolean). It emits the analysis fields, `active_signup_bonuses`, and a customer-facing draft in `response`. Populate qualification fields with evidence-derived strings such as `spend_requirement`, `spend_window`, `eligibility`, `good_standing`, `other_conditions`, and `exclusions`.

Example invocation after creating evidence-derived JSON at runtime:

```sh
python3 scripts/analyze_offers.py < supplied_offers.json
python3 scripts/compose_offer_response.py < supplied_offers.json
```

The helper output is a completeness check, not a substitute for reading the source documents. Correct the final answer if a condition, fee, eligibility restriction, or consumer/business distinction from the source is missing.

## Validation before responding

- The as-of date is within every window described as active.
- The stated leader is an active sign-up bonus, not a recurring earn rate, introductory APR, fee waiver alone, or expired promotion.
- Each USD equivalent for points has an explicitly documented redemption rate, and the original points amount remains visible.
- The leader includes benefit, spend requirement, qualification period, invitation/new-customer restriction, and fee/waiver result where documented.
- Active accessible consumer alternatives include their benefit, threshold, and timing.
- Any business offer is explicitly marked as business-only context and its annual fee is compared only where documented.
- The conclusion explains headline value versus accessibility and, if relevant, annual-fee tradeoffs.
- The answer does not claim current promotion records are unavailable when supplied dated records establish active offers.
