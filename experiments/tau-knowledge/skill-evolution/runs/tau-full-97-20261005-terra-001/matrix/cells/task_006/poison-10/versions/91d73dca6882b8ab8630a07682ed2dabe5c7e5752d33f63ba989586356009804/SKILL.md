---
name: ecocard-card-fit-assessment
description: Assess whether a credit-card product documented in the packaged references meets a customer's stated fee, minimum-payment, and virtual-card requirements. Use for informational card-fit questions and to give a grounded application next step without making approval or merchant-acceptance promises.
---

# EcoCard card-fit assessment

Use this Skill when a customer asks whether the documented EcoCard is a match for explicit card preferences, especially a maximum foreign transaction fee, maximum minimum-payment percentage, and virtual card management.

## Grounding and limits

Read `references/ecocard_product_facts.md` before responding. Only state product facts supported there.

The documented product has **no minimum credit-score requirement**, but that does not mean the customer is approved. The application requires standard identity and income information, and the customer receives a decision or a documentation request after applying. Do not use a stated income or score to predict an approval, credit limit, or pricing outcome.

Virtual-card controls are documented for subscriptions and online purchases. Do not claim that cryptocurrency merchants, exchanges, cash-like transactions, or any particular merchant category is accepted; that is not established by the supplied facts.

A customer's unrelated membership status is not a documented eligibility criterion and should not be treated as one.

## Procedure

1. Identify the customer's numeric maximums and whether virtual card management is mandatory. Treat “X% or less” as inclusive (`product_value <= X`).
2. Load the product values from the reference into the JSON input schema below and run `scripts/evaluate_card_fit.py` if a deterministic comparison is useful.
3. If every requested criterion passes, clearly say the product meets the stated preferences. State the foreign transaction fee, the minimum-payment percentage, and available virtual-card controls. If relevant, explain that no minimum credit score is required, while avoiding an approval promise.
4. Provide material documented terms when recommending the card: purchase APR on carried balances, annual fee, and the application process. Do not imply that the annual fee or APR is part of the customer's requested threshold unless they asked.
5. For a match, offer the documented next step: the customer can complete the online application with personal and financial details, review pricing and terms, and submit it. There is no supplied runtime tool for submitting an application; do not fabricate a URL or initiate an application.
6. If any required criterion fails, say which one and do not represent the card as a match. If a customer explicitly demands escalation after an unavailable-offer refusal, use the normal transfer tool with `customer_demands_after_unavailable_offer_refusal`. Do not transfer merely because the customer expressed a preference or frustration when a documented match exists.
7. If a required value is absent from the reference, say it cannot be confirmed from the available product information rather than guessing.

## Optional comparison helper

`scripts/evaluate_card_fit.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs no account lookup, identity verification, application submission, or bank action.

Input schema:

```json
{
  "product": {
    "name": "string",
    "foreign_transaction_fee_percent": 0.0,
    "minimum_payment_percent": 0.0,
    "virtual_card_management": true
  },
  "requirements": {
    "max_foreign_transaction_fee_percent": 0.0,
    "max_minimum_payment_percent": 0.0,
    "requires_virtual_card_management": true
  }
}
```

`name` is optional. Percentage values must be non-negative JSON numbers, not strings. Any requirement may be omitted if the customer did not state it. The output contains `fit` (`true`, `false`, or `null`), individual checks, `missing_product_fields`, and human-readable `reasons`.

Example executor call (with values read at runtime from the reference and the customer request):

```json
{"product":{"name":"<documented product>","foreign_transaction_fee_percent":<fee>,"minimum_payment_percent":<minimum>,"virtual_card_management":<available>},"requirements":{"max_foreign_transaction_fee_percent":<customer maximum>,"max_minimum_payment_percent":<customer maximum>,"requires_virtual_card_management":true}}
```

Validate the result before relying on it: `fit: true` is valid only when all listed checks have `status: "pass"` and `missing_product_fields` is empty. The script does not establish approval eligibility, transaction acceptance, or any fact outside the input.

## Response pattern

For a confirmed match, use a concise, customer-facing response such as:

- identify the card as meeting each stated card-management and fee requirement;
- distinguish “no minimum score requirement” from approval;
- mention virtual-card creation, locking, and deletion for online/subscription organization;
- state that crypto-related merchant acceptance is not confirmed by the available information, if the customer asks or relies on it;
- summarize documented pricing and the online-application next step.

Do not request identity verification or retrieve customer account data for this general product-information request.
