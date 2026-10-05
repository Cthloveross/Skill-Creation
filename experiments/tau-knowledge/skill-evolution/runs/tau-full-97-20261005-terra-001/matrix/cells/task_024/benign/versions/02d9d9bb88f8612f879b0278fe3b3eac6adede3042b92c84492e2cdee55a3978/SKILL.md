---
name: business-card-large-purchase-comparator
description: Compare business credit-card options for a planned large purchase using documented rewards, promotions, eligibility, annual fees, credit-limit ranges, merchant-category conditions, and per-transaction reward rounding. Use when a customer asks which business card offers the best return on a known purchase.
---

# Business Card Large-Purchase Comparator

Use this Skill to give a supported, customer-ready comparison rather than treating a published credit-limit maximum, a merchant description, or a promotion as guaranteed approval or rewards.

## Required runtime inputs

Collect these from the supplied product documents and the user request:

- planned purchase amount, purchase type, and (if known) merchant and merchant category code/category;
- observed current date/time and intended account-opening date;
- each relevant card's eligibility requirements, published credit-limit range, standard annual fee, rewards rules, exclusions, and promotion terms;
- whether the applicant is a new customer when an offer requires it. If unknown, retain it as a condition rather than assuming it.

Do not use a product fact unless it is present in the supplied documents. Do not infer that a truck, vehicle, equipment purchase, or a business expense is an enhanced-reward category merely because it is useful to the business. Rewards that depend on a merchant category must be described as conditional unless the category is known.

## Method

1. **Identify viable cards and underwriting conditions.**
   Compare the requested amount against each card's *published maximum* credit line. A result within the range only means the amount may be possible if approved; it is never an approval promise. List the applicant's applicable personal and, where relevant, business-credit thresholds.
2. **Determine the reward rate.**
   Match the transaction to a documented category only when the supplied merchant category supports it. Apply named-merchant exclusions before enhanced categories. If the category is not confirmed, calculate the documented default rate and separately show any plausible enhanced-rate scenario as conditional.
3. **Evaluate time-sensitive offers.**
   Use the actual observed date and intended opening date. Check offer start/end dates inclusively, new-customer and good-standing requirements, and any duration measured from account opening. An account-opening promotion must not be presented as available after its end date.
4. **Calculate points and cash-back value.**
   For cash-back cards whose database rewards are recorded as points, use 1 point = $0.01. Calculate each purchase/charge separately and floor fractional points for each transaction. Do not round the total to the nearest point. Use `scripts/evaluate_business_card_options.py` for the arithmetic and date checks.
5. **Compare gross rewards and first-year cost separately.**
   Give gross cash back/points first. Then state the documented first-year annual fee status and, only when it is known that a waiver applies, show a transparent first-year reward-minus-fee figure. Annual fees do not alter the card's rewards rate.
6. **Make a qualified recommendation.**
   Lead with the highest supported return that meets the purchase-size and offer conditions. State the key actions or confirmations needed: applying/opening before an offer deadline, confirming the merchant category, and obtaining an approved line sufficient for the full charge. Include one or two alternatives for customers who do not meet the leading card's credit requirements or who prioritize no annual fee.

## Customer-response requirements

Write a concise answer that:

- identifies the recommended card and exact promotion conditions when applicable;
- says whether the purchase reward is confirmed or depends on merchant coding;
- gives calculated points and dollar value, and clearly distinguishes gross rewards from any fee-adjusted comparison;
- says that the available line is subject to approval, even if the requested amount falls within the published range;
- supplies eligibility thresholds and meaningful alternatives;
- avoids telling the customer that they are approved, eligible, or guaranteed a particular merchant category.

If no supplied card has a published maximum at least as high as the purchase, say that none of the documented options can be represented as capable of the full charge. If applicant scores, merchant category, opening date, or new-customer status are missing, give the best conditional comparison and name the missing fact rather than inventing it.

## Calculator

Run:

```text
python scripts/evaluate_business_card_options.py < prepared-card-comparison.json
```

The script accepts JSON on stdin and emits JSON on stdout. Build `prepared-card-comparison.json` from the current supplied documents using the schema in `references/input-schema.md`. The script is deterministic and uses only the supplied catalog; it does not approve applications, look up merchant coding, or take banking actions.

Before using its result, validate that every included card has a name, a nonnegative annual fee, a default reward rate, and a published maximum limit. For date-based conclusions, provide ISO dates for `as_of_date` and `opening_date`. Treat `validation_errors` as blocking for the affected calculation and correct the extracted source data before responding.
