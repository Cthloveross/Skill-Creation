---
name: credit-card-referral-link-triage
description: Safely handle requests for a credit-card referral link. Use when a customer asks how to generate or share a referral link and the available knowledge base must be checked for an active, card-specific referral offer and matching terms.
---

# Credit Card Referral Link Triage

Use this Skill before giving a customer the referral-link tool. A card account being present does **not** establish that the card has a documented active referral program.

## Required assessment

1. Identify the exact card name and the terms the customer claims (bonus, qualification, time period, and any other conditions).
2. Search the available knowledge base for a documented referral program for that exact card.
3. Compare the customer's claimed terms with the documented terms for that card.
4. If a program is documented and the terms match, check whether there is reason the referral would be automatically rejected. In particular, a customer can receive no more than two referral bonuses in a rolling seven-day period; later referrals in that window are automatically denied. Use available referral records when needed.
5. Run `scripts/referral_decision.py` with the conclusions from the preceding checks to produce a consistent decision and response outline.

## Decision rules

- If no active, card-specific referral program is documented, explain that the requested card does not have a documented active referral offer. Do **not** give a referral-link tool and do not transfer the customer.
- If the claimed terms do not match the documented card-specific terms, explain the discrepancy and restate only the documented terms. Do **not** give a referral-link tool and do not transfer the customer.
- If the referral would be automatically rejected (including the rolling seven-day bonus limit), explain why. Do **not** give a referral-link tool and do not transfer the customer.
- Only when all checks pass, tell the customer the correct documented terms and provide the user-executable tool via `give_discoverable_user_tool`:
  - `discoverable_tool_name`: `get_referral_link`
  - `arguments`: `{}`

Do not call `get_referral_link` yourself. Tell the customer to run it with their own `user_id` and the exact documented card name. A successful customer call creates a referral with status `NO_PROGRESS`; the referred person may then apply using the generated link.

## Customer communication

Use a clear response that states the outcome and relevant reason. For an approved request, reiterate the documented terms and the rolling seven-day limit before providing the tool. Do not invent bonus amounts, spending thresholds, eligibility criteria, or offer status from a generic referral article or from account records.

A generic statement that offers vary by card is not documentation of an offer for a particular card. Where the available sources contain no card-specific program and no matching terms, decline without a tool.

## Script interface

Run the deterministic helper as follows:

```text
python scripts/referral_decision.py <<'JSON'
{"card_name":"Exact card name","program_documented":true,"terms_match":true,"automatic_rejection_risk":false,"documented_terms":"Optional customer-safe documented terms"}
JSON
```

It reads one JSON object from standard input and writes one JSON object to standard output. `program_documented`, `terms_match`, and `automatic_rejection_risk` are required booleans. The script returns `outcome` (`decline` or `offer_tool`), whether a referral tool may be provided, and a response outline. Treat an input-validation error as a stop condition: gather or clarify the missing assessment rather than providing the tool.

## Validation

Before acting on an `offer_tool` result, confirm all three gates in its output are true/false as required: documented program is true, terms match is true, and automatic rejection risk is false. For every `decline` result, verify that no discoverable referral tool was provided.
