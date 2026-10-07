---
name: credit-card-fit-screening
description: Compare documented credit-card terms with a customer's stated feature requirements and disclosed eligibility details. Use for informational product recommendations, not to apply for, open, or manage a credit-card account.
---

# Credit-Card Fit Screening

Use this Skill for a customer asking which card matches requirements such as a maximum foreign-transaction fee, maximum minimum-payment percentage, virtual-card availability, credit score, income, or membership status.

## Scope and safety

- This is an informational comparison, not a banking action. Do not submit an application, perform a credit pull, open or activate a card, change account data, schedule a payment, or redeem rewards.
- A customer-provided score, income, and subscription status are stated facts for the comparison only. Do not represent a fit as approval or an approval guarantee.
- A missing customer record only prevents retrieval of account-specific data. It does not make public product documentation unavailable and does not justify declining to compare documented products.
- Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Evidence-first workflow

1. Extract the customer's explicit must-haves and eligibility facts. Preserve inclusive bounds: a requirement of “1.5% or less” accepts exactly `1.5%`.
2. **Inspect the supplied product documents before making any availability claim.** Treat documents in the current task context as the product source of truth. Do not say that terms are unavailable merely because there is no customer account record or no account-specific tool result.
3. For each relevant card, gather documented facts across all of its documents. Record both the value and its source document. Keep a field unknown when it is not documented; never substitute APR, rewards rate, or another percentage for a minimum-payment or foreign-transaction-fee percentage.
4. Screen the normalized facts with `scripts/screen_cards.py`, or use `scripts/screen_documents.py` when the input is a list of raw product documents.
5. Recommend every `documented_fit`: it meets every confirmed requested feature and has no known disclosed eligibility blocker. Unknown non-requested underwriting criteria do not erase a documented fit, but must be disclosed as an approval limitation.
6. Do not recommend a card as a match if it fails a requested feature or has a known blocker such as a stated score below a documented minimum, a missing required membership, or invitation-only access.
7. Explain the result using every requested constraint, then state that the comparison is not an approval decision.

## Required customer-facing content

For each recommendation, state:

- the card name;
- the documented foreign-transaction fee and how it compares with the requested cap;
- the documented minimum payment and how it compares with the requested cap;
- whether virtual-card management is available;
- why the stated score and membership do or do not encounter a disclosed requirement; and
- that final approval can require identity, income, and underwriting review.

If a crypto-rewards card or any other appealing alternative is mentioned but is blocked by a documented score or membership requirement, explicitly identify that blocker and do not characterize it as available to the customer.

A suitable response structure is:

> Based on the information you provided, **[card]** is the documented fit. Its foreign transaction fee is **[fee]**, its minimum payment is **[payment]** of the outstanding balance, and virtual card management is **[available/unavailable]**. **[Explain score and membership comparison.]** This means you can apply based on the disclosed requirements, not that approval is guaranteed; final approval is determined during application and underwriting.

## Normalized screening script

Run:

```text
python3 scripts/screen_cards.py < input.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "customer": {
    "credit_score": 540,
    "annual_income": 95000,
    "subscriptions": []
  },
  "criteria": {
    "max_foreign_transaction_fee_pct": 1.5,
    "max_minimum_payment_pct": 1.5,
    "requires_virtual_card_management": true
  },
  "cards": [
    {
      "name": "Card name",
      "foreign_transaction_fee_pct": 1.0,
      "minimum_payment_pct": 1.0,
      "virtual_card_management": true,
      "minimum_credit_score": 0,
      "subscription_requirement": "none",
      "invitation_only": false,
      "minimum_annual_income": null,
      "source_notes": ["Document title or identifier"]
    }
  ]
}
```

`customer`, `criteria`, and `cards` are required. Numeric facts may be `null` only when not documented. `minimum_credit_score: 0` is valid only when the source explicitly states that there is no score requirement. `subscription_requirement` is `"none"`, `"unknown"`, a subscription name, or a list of names.

The output has `assessments`, `recommendations`, and `alternatives`. A recommendation has `tier: "documented_fit"`; inspect its `preference_results`, `eligibility_blockers`, and `eligibility_unknowns` before drafting the response.

## Raw-document helper

When product documents are supplied directly, run:

```text
python3 scripts/screen_documents.py < input.json
```

Input has the same `customer` and `criteria` objects plus:

```json
{
  "documents": [
    {"document_id": "optional-id", "title": "Card Name: document title", "content": "document text"}
  ]
}
```

The helper groups facts by the card-name prefix in document titles, extracts common labeled card terms, preserves source identifiers, and invokes the normalized screener. Review `extraction_warnings` and the emitted normalized `cards`: automated extraction is an aid, not a reason to omit a clearly documented term visible in the source.

## Validation before responding

- Confirm each recommended card has `pass` for every requested feature and an empty `eligibility_blockers` list.
- Confirm that all relevant supplied product documents were inspected, especially documents with application/eligibility terms and payment/management terms.
- Include source-backed values for each requested feature rather than a bare product name.
- State known blockers for alternatives; do not conceal a score or subscription mismatch.
- Do not state or imply approval.
- If no documented fit exists, say so and identify the exact failed feature or eligibility blocker for the closest alternatives.
