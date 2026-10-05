---
name: credit-card-promotion-comparison
description: Answer informational requests comparing date-current credit-card sign-up bonuses, statement credits, cash back, points, annual-fee waivers, and introductory APR offers. Use when supplied promotion records and a current-time observation must be turned into a qualification-aware comparison; do not use to apply for, open, modify, or service an account.
---

# Credit Card Promotion Comparison

Use this skill to give a direct, date-accurate answer when a customer asks which credit-card promotions or sign-up bonuses are available, especially when they prioritize cash back or points.

## Scope and safety

This is an informational workflow. Do not collect identity information, retrieve a customer profile, estimate approval odds, request an invitation, or take an account action merely to answer an offer question. Do not say a customer qualifies unless every documented condition has been independently established.

If the request changes into a banking action, preserve this prerequisite verbatim in the resulting banking procedure and use the execution agent's normal banking tools:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required inputs

Read the current task's supplied promotion documents and successful read-only current-time observation. The supplied documents are usable promotion records even though the customer has not supplied identity or account details. A missing customer profile is **not** a reason to claim that current offers cannot be confirmed.

For each relevant document, record at runtime:

- card and whether it is consumer or business;
- promotion type: sign-up bonus, introductory APR, fee waiver, or other;
- explicit start and end dates, and which event must occur within them;
- reward amount, unit, payout form, and any documented point redemption value;
- invitation-only, new-customer, good-standing, spend, timing, and eligible/net-purchase conditions;
- material exclusions, fee waiver, fulfillment, standard fee, or standard APR details.

Use offer-specific documents for the offer window and conditions. Application or product documents can corroborate a bonus, but must not silently extend an explicit campaign window.

## Required method

1. **Set the as-of date.** Extract the local calendar date from a supplied successful time observation. Offer dates are inclusive. If there is no reliable time observation, say that current status cannot be determined from the supplied information.
2. **Classify all dated records.** An offer is active only when the as-of date is within its explicit date window. Mark records outside their window as upcoming or expired. If dates are missing, malformed, contradictory, or govern another benefit, label status unknown; never assume it is active.
3. **Identify the requested offers.** For a request about sign-up bonus value, list active sign-up bonuses first. Keep active 0% APR and standalone fee-waiver offers separate because they are not sign-up bonuses.
4. **Rank only with support.** Rank direct cash, cash-back, and statement-credit bonuses by documented USD amount. Convert points to USD only where the supplied records explicitly give a redemption rate. Preserve the points terminology even when showing its documented equivalent. Do not mistake an earn rate for a sign-up bonus.
5. **Account for attainability.** State invitation-only restrictions, new-customer restrictions, spend thresholds, qualifying periods, and good-standing requirements. A face-value leader must not be presented as generally obtainable when it requires an invitation or unusually high short-term spend.
6. **Answer directly.** When records establish active offers, provide their actual values and conditions. Do not decline, say records are unavailable, or ask the customer to supply promotion details already present in the task evidence.

## Minimum response coverage

For every active sign-up bonus included in the comparison, state:

- card name;
- bonus amount and whether it is a statement credit, cash back, or points;
- that it is active as of the observed date or its applicable current window;
- documented spend threshold and qualifying period;
- invitation-only or new-customer restriction, if documented; and
- good-standing, eligible/net-purchase, return, credit, or other material conditions.

For the highest documented face-value bonus, use an explicit comparison term such as **largest**, **highest**, **best by documented bonus value**, or **top**. In the same discussion, explain why it may not be the best accessible option. Include a currently active, non-invitation alternative where the supplied records establish one.

A suitable answer structure is:

```text
As of [observed date], the largest active sign-up bonus by documented value is
[card]: [reward and any included benefit]. It requires [all material conditions]
and is [invitation/new-customer limitation].

Other active sign-up options:
- [card]: [reward] after [threshold] in [period], available to [eligibility group]
and subject to [material conditions].

Bottom line: [leader] has the highest headline value, but [reason it is less
accessible]. [alternative] has a lower bonus but is the more practical option
for a qualifying new customer who does not have an invitation or cannot meet the
higher spend requirement.
```

State current date windows where they clarify why an offer is currently available. Do not claim an invitation will be issued or an application will be approved. If business-card records are active, distinguish them clearly from consumer cards rather than implying a consumer applicant can use them.

## Deterministic helpers

### `scripts/analyze_offers.py`

Use this helper to categorize structured promotion records and rank active sign-up bonuses. It reads one JSON object from stdin and emits one JSON object on stdout. It makes no network calls and does not access customer information.

Input fields:

- `as_of`: required string beginning with `YYYY-MM-DD`;
- `offers`: required array of records with `card`, `offer_type`, `window_start`, `window_end`, `reward`, and optional qualification and fulfillment data;
- `reward.kind`: `statement_credit`, `cash_back`, `cash`, `points`, or `other`;
- `reward.amount`, `reward.currency`, and, only when documented, `reward.redemption_value_per_point`;
- `qualification`: optional object containing invitation, new-customer, spend, good-standing, and exclusions fields.

Its output contains `ranked_active_signup_bonuses`, `active_non_signup_offers`, `inactive_or_unknown_offers`, `warnings`, and `errors`. Points without a documented conversion are retained but not ranked against USD.

### `scripts/compose_offer_response.py`

Use this helper after transcribing the applicable evidence into the same structured records. It produces a customer-facing draft in `response`, plus the active records and warnings used to build it. The input additionally accepts optional `product_scope` (`consumer`, `business`, or `all`) and `include_non_signup` (boolean). For readable output, populate `qualification` with strings such as `spend_requirement`, `spend_window`, `eligibility`, `other_conditions`, and `exclusions`, and populate `supplemental_benefits` when an offer includes a fee waiver or another separately documented benefit.

Build JSON only from the current task's records, then run either helper as appropriate:

```sh
python3 scripts/analyze_offers.py < supplied_offers.json
python3 scripts/compose_offer_response.py < supplied_offers.json
```

Treat helper output as a chronology and completeness check. Compare it against the source records before responding, and correct any missing condition in the final response.

## Validation before responding

- Confirm the observed as-of date falls within each offer called active.
- Confirm the stated leader is a sign-up bonus, not introductory APR, a recurring earn rate, or an expired offer.
- Confirm any USD comparison of points uses a documented redemption value.
- For the leader, include value, spend threshold, qualification period, and invitation/new-customer limitation where documented.
- Include active accessible alternatives with their value, threshold, and timing.
- Explain the maximum-value versus accessibility tradeoff.
- Do not call records unavailable when dated supplied records establish active offers.
- Keep expired, upcoming, and unknown-status promotions out of statements about what is currently available.
