---
name: flat-rate-credit-card-recommendation
description: Recommend and compare personal credit cards for a customer who wants simple everyday cash back, especially when annual-fee, subscription, category-reward, and credit-score constraints must be distinguished. Use for informational product advice only; it does not apply for, open, modify, or service an account.
---

# Flat-Rate Credit Card Recommendation

## Scope and safety

Use this Skill to give a source-grounded product recommendation. It is not an approval decision, credit decision, or promise of eligibility. Do not submit an application, initiate a credit pull, access an account, redeem rewards, or perform another banking action as part of this workflow.

Treat an unknown credit score, unverified subscription status, or missing product term as a condition to verify, not as evidence that the customer qualifies. Do not infer a card's rewards, fees, or eligibility criteria from its name.

## Runtime input to collect

From the current conversation, identify:

- Whether the customer wants flat/simple rewards rather than category-based rewards.
- The maximum acceptable **card annual fee**.
- Whether an otherwise-required membership is already active. Record this separately from the card annual fee; an employer-provided membership may satisfy a subscription requirement even if it normally has a price.
- Credit score or score range, if supplied. A missing score remains unknown.
- Spending categories only when they are reliably supplied. Do not fabricate a spending mix.
- Any explicit exclusions, such as unwillingness to pay a membership, travel not being personally paid, or a desire for a particular redemption type.

From the supplied product material, build one card object per plausible personal card. Normalize a flat cash-back rate to a percent number and identify whether it applies to all eligible purchases. Use the currently applicable standard card fee unless a dated promotion is both relevant and valid as of the supplied current date. Keep document IDs or concise source notes with each extracted card for traceability.

Use `flat_all_eligible` only when the source supports a flat rate on all eligible/everyday purchases. Classify category-specific, rotating, or mixed-rate products as `category_or_mixed`; do not present them as equivalent to a flat-rate card merely because their top category rate is higher.

## Ranking procedure

1. Exclude cards whose known annual card fee exceeds the customer's maximum, whose known reward structure conflicts with a stated flat-rate preference, or whose required subscription is known inactive.
2. For remaining cards, assess the subscription requirement and minimum credit score independently:
   - A known score below the minimum is an exclusion.
   - A missing score makes the recommendation conditional on meeting the stated minimum.
   - An unknown or unverified required membership makes the recommendation conditional on it being active.
3. Rank eligible and conditional flat-rate cards by cash-back rate. A conditional higher-rate card may be the best fit, but label the unmet/unknown condition prominently and also mention any lower-rate alternative that has a lower known score threshold.
4. Do not claim that a card is “best” solely from a promotional rate, a category rate, a rewards redemption value unrelated to earning rate, or an unverified term.
5. Run the packaged helper to make filtering, eligibility labels, and ordering deterministic.

Example invocation (with values extracted at runtime, not copied from this example):

```json
{"preferences":{"simple_flat_cashback":true,"max_annual_fee":"0","credit_score":null,"subscription_status":{"Membership Name":"active"}},"cards":[{"name":"Card name","cash_back_rate":"2.5","cash_back_scope":"flat_all_eligible","annual_fee":"0","required_subscription":"Membership Name","min_credit_score":720,"source_notes":["product terms"]}]}
```

Send that JSON to `scripts/rank_cards.py`. The script reads one JSON object from standard input and emits one JSON object to standard output. It does not access customer data, tools, network services, or accounts.

## Helper input and output schema

Required top-level keys:

- `preferences` object:
  - `simple_flat_cashback` (boolean)
  - `max_annual_fee` (number or numeric string)
  - `credit_score` (number or `null`)
  - optional `subscription_status` object mapping membership name to `active`, `inactive`, or `unknown`
- `cards` array, where every card has `name`, `cash_back_rate`, `cash_back_scope`, and `annual_fee`. Optional fields are `required_subscription`, `min_credit_score`, and `source_notes`.

The output has:

- `recommendations`: cards not disproven by the constraints, ordered by flat cash-back rate, with `eligibility` of `eligible` or `conditional` and explicit `conditions`.
- `excluded`: cards that conflict with a known preference or known eligibility fact, with `reasons`.
- `validation_errors`: malformed or incomplete input fields. Resolve these from source material before relying on the ranking.

A nonempty `validation_errors` result means the associated candidate must not be used as a definitive recommendation. A successful response can still contain zero recommendations; state that the supplied terms do not establish a match rather than guessing.

## Customer-facing response

Give a concise answer that:

1. Names the highest-ranked fit and states its flat rate and annual card fee.
2. Separately discloses any required active membership and the minimum score threshold.
3. If the score is unknown, says that the choice is conditional on meeting that threshold; do not ask the customer to disclose more than they wish to share.
4. Briefly explains why materially lower-ranked cards were not preferred (for example, lower flat rate, annual fee, or category-based rewards).
5. Distinguishes a card annual fee from a separate membership charge, and notes any membership charge only if supported by the product material.
6. Uses qualifying language such as “based on the terms provided” and “subject to underwriting/approval.”

If the customer asks how to apply after receiving advice, provide only the documented high-level application steps and terms. Do not carry out the application or represent that the customer will be approved.
