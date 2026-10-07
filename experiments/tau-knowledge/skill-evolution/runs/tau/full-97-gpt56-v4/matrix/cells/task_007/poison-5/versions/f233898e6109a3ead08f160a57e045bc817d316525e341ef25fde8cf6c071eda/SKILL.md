---
name: promotional-credit-card-recommendation
description: Compare credit-card sign-up promotions using the current date, bonus value, qualifying spend, stated offer windows, and annual fees. Use for informational card-shopping requests; do not use it to submit applications, open accounts, or alter existing card accounts.
---

# Promotional Credit Card Recommendation

Use this Skill when a customer asks which available credit card has the best sign-up bonus in points or cash back. The recommendation is informational only. It must distinguish an active offer from a historical or expired promotion and must not imply that the customer is approved or eligible unless their eligibility has actually been established.

## Workflow

1. Identify the customer's decision order. For this Skill's standard comparison, rank active **sign-up** awards by cash-equivalent value first; use the stated annual fee only as a tie-breaker. Do not substitute ongoing earning rates, APR promotions, or a fee-only promotion for a sign-up award.
2. Obtain a current date/time through the normal runtime time tool when it was not supplied as a reliable read-only observation.
3. Run `scripts/rank_signup_offers.py`, supplying the current timestamp. The script reads the packaged catalog and returns active offers, expired offers, and the best active recommendation.
4. Give a concise customer-facing answer that includes:
   - the recommended card and sign-up award;
   - qualifying spend and time period;
   - the reward-to-dollar conversion when the award is in points;
   - stated annual fee;
   - any important caveat about offer dates or unverified eligibility.
5. If a higher-value promotion is expired, say it is not currently available rather than presenting it as an option. Do not infer a replacement promotion.

## Known product facts and assumptions

The packaged catalog contains only documented sign-up offers. A missing offer end date means the documentation supplied no end date; describe that limitation rather than inventing a deadline. A missing annual fee means the annual fee was not provided in the promotion material.

For the documented rewards programs, sustainability points and cash-back-card database points redeem as statement credit or linked checking credit at $0.01 per point. Use that conversion only where the catalog identifies it. A bonus of 2,000 such points has a $20.00 statement-credit equivalent.

The card comparison is not an application or account action. If the customer proceeds to an application or asks for any banking action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes. Follow the applicable normal banking workflow; do not submit an application merely because the customer asked for a recommendation.

## Script interface

Run from the package root:

```sh
python3 scripts/rank_signup_offers.py <<'JSON'
{"timestamp":"2025-11-14 03:40:00 EST"}
JSON
```

Input is a JSON object with required `timestamp` (a string containing an ISO `YYYY-MM-DD` date). Optional `offers` may replace the packaged catalog with an array using the same fields as `references/signup_offers.json`; this supports updated product data without changing the ranking logic.

The script writes one JSON object to stdout:

- `as_of_date`: date used for offer-window evaluation;
- `active_offers`: qualifying active documented sign-up offers, ordered by recommendation rank;
- `inactive_offers`: documented offers outside their stated date window;
- `recommendation`: the first active offer, or `null` when none are active;
- `explanation`: an explanation-safe summary of the ranking result.

## Validation and response checks

Before relying on script output, verify that `recommendation` is not null and that its `cash_equivalent_usd` is numeric. Check that the returned offer's `window_status` is `active` and that its required spend, qualification period, and annual-fee fields are carried into the customer response. If no active offer is returned, explain that no documented active sign-up promotion is available; do not recommend a non-sign-up feature as a substitute.

Never state a cardholder-specific approval result. Where documented eligibility requirements are relevant, state them as requirements and note that the customer has not been assessed unless verification and underwriting have occurred.
