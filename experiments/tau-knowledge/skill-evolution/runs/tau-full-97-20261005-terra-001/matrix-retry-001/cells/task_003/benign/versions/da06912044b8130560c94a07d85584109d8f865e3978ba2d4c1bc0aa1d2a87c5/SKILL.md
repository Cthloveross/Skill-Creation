---
name: evidence-grounded-credit-card-advisor
description: Recommend or compare credit cards from product documents supplied with the current task. Use for customer requests involving rewards, travel spending, foreign transaction fees, purchase protection, credit-limit potential, fees, or eligibility.
---

# Evidence-Grounded Credit Card Advisor

## Scope

Use the supplied product documents as the factual card catalog. Provide a grounded recommendation or comparison; do not access an account, retrieve external offers, obtain a credit report, make an underwriting decision, submit an application, or guarantee approval.

When the current task supplies product documents, they are available evidence. Do not claim that card terms, a catalog, or product information are unavailable merely because they were supplied as task documents rather than by an external lookup.

## Required response behavior

As soon as the customer gives enough criteria to compare products, provide the recommendation in the first substantive reply. Do not wait for identity verification, income, credit score, an annual-fee preference, or another follow-up question.

For a request with a supplied catalog, **run `scripts/catalog_advice.py` before drafting the first substantive answer**. Pass the customer's request as `opening` and the supplied document list as `documents`. Use its `message` when `validation.send_ready` is true, checking it against the cited card facts before sending. The script performs analysis only; it does not apply for a card or take any banking action.

A reply recommending a card must:

1. Name at least one documented option and clearly recommend it or present it as an option.
2. Address every customer hard requirement using facts belonging to that same card.
3. State reward rate and scope, relating them to the stated everyday and/or travel spending pattern when documented.
4. For a no-foreign-fee need, state the documented `0% foreign transaction fee` and any condition that controls it.
5. For a protection need, state **purchase protection** and its documented coverage window and claim cap or unlimited coverage when available.
6. For a requested credit limit, state the documented range or maximum and explain that the requested amount is possible only if it falls within that range or ceiling.
7. State that approval and the actual assigned limit are subject to underwriting.
8. Disclose material documented restrictions of the recommended card, including an annual fee, minimum score, required subscription, invitation-only access, or policy exclusions where applicable.

Do not transfer the customer merely to avoid giving a documented recommendation.

## Evidence and selection rules

- Build facts separately per card. Never combine a reward from one card with protection, fees, or limits from another.
- Treat absent evidence as unknown, not favorable.
- A card meets a no-foreign-transaction-fee requirement only when its own documents support 0%. If the rate depends on a subscription or other condition, make the condition prominent.
- A card meets a possible-limit requirement only when its own documented maximum or range reaches the requested amount. A range establishes possibility, never a promise.
- A card meets a purchase-protection requirement only when its own documents expressly provide it. Preserve documented terms and exclusions.
- Rank cards meeting the hard requirements by the documented fit to the stated spending pattern. A flat rate on all eligible purchases is generally a clear fit for travel-heavy spending with lower miscellaneous everyday purchases because it covers both without assuming merchant-category coding.
- Do not invent category bonuses, approval odds, redemption values, fees, protections, or eligibility rules.

If several cards qualify, give one direct primary recommendation and optionally mention alternatives. Every alternative must independently meet the hard requirements, and its material eligibility caveat must appear alongside it. If no card qualifies, identify which required fact is missing or unmet for each plausible card; do not represent any as a match.

## Runtime helper

`scripts/catalog_advice.py` accepts JSON on stdin:

- `opening` (string): the customer's request.
- `documents` (array): current-task product documents, each with `document_id`, `title`, and `content` strings.

Run:

```bash
python3 scripts/catalog_advice.py < task_input.json
```

It emits JSON on stdout with:

- `message`: a customer-facing primary recommendation or an evidence-based no-match explanation;
- `primary_card`: selected product name or `null`;
- `qualified_cards` and `rejected_cards`: per-card requirement checks;
- `validation`: whether the recommendation includes all detected hard requirements.

If input is malformed, the script emits `{"error": "..."}`. In that case, inspect the supplied documents directly rather than making unsupported claims.

## Final send check

Before sending, confirm that the response itself:

- names a qualifying documented card;
- connects documented rewards to the customer's spending pattern;
- includes each applicable hard requirement, especially `0% foreign transaction fee`, **purchase protection**, and a qualifying limit range or maximum;
- says a requested limit is possible rather than guaranteed and remains subject to underwriting and approval;
- keeps benefits attached to their correct product;
- discloses material restrictions; and
- does not claim supplied product information is unavailable.
