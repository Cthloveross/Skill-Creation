---
name: personal-cash-back-card-recommendation
description: Recommend a Rho-Bank personal cash-back card using stated spending pattern, annual-fee preference, subscription access, credit-score information, and current date. Use for prospective-card advice; do not use it to approve an application or reveal account data.
---

# Personal Cash-Back Card Recommendation

Use this Skill to give a concise, evidence-grounded recommendation for a customer choosing a personal card. It distinguishes a card annual fee from any required Rho-Bank+ membership and does not represent conditional eligibility as approval.

## Required inputs

Collect or infer the following from the conversation:

- `spending_focus`: `general`, `travel_software`, or `mixed`
- `avoid_annual_fee`: boolean
- `premium_subscription_access`: `yes`, `no`, or `unknown`
- `credit_score`: an integer when supplied, otherwise omit or use `unknown`
- `current_date`: ISO date if promotional timing could matter

For this task, the public clarifications are sufficient. Do **not** ask again for a monthly spend amount when a rate comparison alone determines the recommendation. If the score is unknown, give a conditional recommendation and state that underwriting determines approval.

## Procedure

1. Read `references/card_facts.md` before advising. Treat it as the available product evidence; do not invent category bonuses, approval rules, or promotions.
2. Identify whether the customer wants broad everyday/general purchases. For general spending, compare the flat general-purchase rates rather than category-specific travel/software rates.
3. Apply the annual-fee constraint. A customer who avoids an annual card fee should normally be directed to a no-card-annual-fee option. Clearly call out that Gold still requires Rho-Bank+ even though its card annual fee is $0.
4. Check known prerequisites:
   - Gold needs active Rho-Bank+ and a 720 minimum score.
   - If a score is not known, phrase Gold as the leading option **if the applicant meets the 720 requirement**, not as an approval prediction.
   - A lower-score fallback must likewise be conditional on its documented minimum.
5. Use the current date for time-bounded offers. Never treat the Platinum first-year waiver as available outside its stated 2024 window.
6. Provide a direct recommendation, the principal condition/caveat, and one useful fallback. Include rates and fees relevant to the customer, without overwhelming the customer with unrelated card terms.

## Generating a consistent response

Run:

```text
python3 scripts/recommend_card.py <<'JSON'
{"spending_focus":"general","avoid_annual_fee":true,"premium_subscription_access":"yes","credit_score":"unknown","current_date":"2025-11-14"}
JSON
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Its schema is:

- Input: the fields listed in **Required inputs**. `credit_score` may be an integer, numeric string, `unknown`, or omitted. `current_date` may be omitted.
- Output: `{ "recommendation": string, "recommended_card": string|null, "eligibility_status": string, "alternatives": [string], "warnings": [string], "facts_used": [string] }`.

Use `recommendation` as the customer-facing core response. You may add a short, neutral invitation to share a score range if the output says it is unknown. Do not say a card will be approved.

## Validation

Before sending the answer, verify that it:

- names the recommended card and its applicable cash-back rate;
- states the card annual fee when annual-fee preference is relevant;
- says Gold requires Rho-Bank+ and at least a 720 score when Gold is discussed;
- uses conditional language for unknown or unmet score requirements;
- does not recommend an expired Platinum fee waiver; and
- does not claim that a subscription is free unless the customer specifically states that they receive it without cost.

If necessary inputs are missing, provide the best conditional comparison rather than fabricating them. This is informational advice only; the issuer makes final underwriting and offer decisions.
