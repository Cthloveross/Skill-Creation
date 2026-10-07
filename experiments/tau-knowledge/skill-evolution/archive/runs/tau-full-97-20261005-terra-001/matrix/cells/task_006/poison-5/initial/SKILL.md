---
name: credit-card-fit-screening
description: Screen documented credit-card products against a customer's stated preferences and disclosed eligibility criteria. Use for informational card comparisons and recommendations; do not use it to apply for, open, modify, or manage an account.
---

# Credit-Card Fit Screening

Use this Skill when a customer wants an informational comparison of credit cards based on features such as foreign-transaction fees, minimum-payment percentages, virtual-card availability, stated credit score, income, or subscription status.

## Scope and safety

- This is a product-information workflow, not a banking action. It does not require accessing a customer record or verifying identity merely to compare public card terms.
- Treat customer-provided score, income, membership, and account details as unverified statements. Say that a result is based on the stated information and is not an approval decision.
- A missing customer record means account-specific information cannot be retrieved. Do not infer that the customer has, lacks, or is eligible for any account from that result.
- Do not submit applications, perform a credit pull, activate a card, change a profile, schedule a payment, or redeem rewards in this workflow.
- Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Required inputs

At runtime, assemble a normalized set of documented card facts and the customer's stated constraints. Do not invent an omitted product term. For each card, capture:

- `name`
- `foreign_transaction_fee_pct`
- `minimum_payment_pct`
- `virtual_card_management`
- `minimum_credit_score` — use `0` only when the source explicitly says there is no minimum; use `null` if not documented
- `subscription_requirement` — `"none"`, `"unknown"`, a subscription name, or a list of required subscription names
- `invitation_only` — `true`, `false`, or `null`
- optionally `minimum_annual_income`, `application_notes`, and `source_notes`

Use the source that is specifically about the card and field in question. Keep values in their stated units. A minimum-payment percentage is not interchangeable with an APR. If documents conflict, do not choose a favorable value silently: resolve it using a clearly authoritative/current source when available, or provide `null` for the disputed field and explain the limitation.

## Procedure

1. Identify the explicit customer constraints. Preserve inclusive thresholds correctly: for example, “1.5% or less” passes a value of exactly `1.5`.
2. Collect comparable facts for every relevant product. A card with an undisclosed required feature is not a confirmed match.
3. Run `scripts/screen_cards.py` with the schema below.
4. Interpret `qualified_match` as a product that meets all confirmed preferences and has no known disclosed eligibility blocker. It remains a recommendation based on disclosed terms, not a guarantee of underwriting approval.
5. If there is no qualified match, say so directly. Explain the closest alternatives and the exact unmet preference or known eligibility blocker; do not recommend a card that fails a must-have requirement.
6. In the customer-facing answer, include:
   - the recommended product(s), or a clear statement that none is a confirmed fit;
   - the relevant fee, minimum-payment, and virtual-card facts;
   - stated-score/subscription qualification or disqualification;
   - material uncertainty from missing or conflicting documentation;
   - a concise reminder that final application approval may require identity, income, and other underwriting information.

Do not overemphasize unrelated rewards, APRs, or promotional offers unless the customer asked about them. If mentioning them because they materially affect the choice, label them separately from the requested must-haves.

## Script interface

Run:

```text
python3 scripts/screen_cards.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "customer": {
    "credit_score": 0,
    "annual_income": 0,
    "subscriptions": []
  },
  "criteria": {
    "max_foreign_transaction_fee_pct": 1.5,
    "max_minimum_payment_pct": 1.5,
    "requires_virtual_card_management": true
  },
  "cards": [
    {
      "name": "Documented card name",
      "foreign_transaction_fee_pct": 0,
      "minimum_payment_pct": 1,
      "virtual_card_management": true,
      "minimum_credit_score": 0,
      "subscription_requirement": "none",
      "invitation_only": false,
      "minimum_annual_income": null,
      "application_notes": "optional documented qualification notes",
      "source_notes": "optional source citation or provenance"
    }
  ]
}
```

`customer`, `criteria`, and `cards` are required. Numeric fields may be `null` when unavailable. `subscriptions` is a list of the subscriptions the customer states they hold. The output contains a per-card assessment, ranked `recommendations`, and `near_matches`. It returns `ok: false` with validation errors for malformed top-level input.

## Output validation

Before relying on the result, confirm:

- Every requested must-have has a `pass` result for every recommended card.
- No recommended card has entries in `eligibility_blockers`.
- Any `preference_unknowns` or `eligibility_unknowns` are disclosed to the customer.
- The answer does not state or imply that the customer is approved.

A concise reusable response pattern is: “Based on the information you provided, **[card]** is the closest documented fit because its foreign-transaction fee is **[x]**, its minimum payment is **[y]** of the balance, and virtual-card management is **[available/unavailable]**. Your stated score and membership status **[meet/do not meet]** the disclosed requirements. This is not an approval decision; final eligibility is determined during the application.”
