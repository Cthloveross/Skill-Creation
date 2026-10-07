---
name: credit-card-criteria-comparison
description: Compare documented credit-card products against a customer's stated eligibility and feature constraints, identify only supported matches, and communicate a safe informational recommendation or appropriate transfer path. Use for card-shopping questions; not for opening, changing, or servicing an account.
---

# Credit Card Criteria Comparison

Use this Skill when a customer asks which credit-card offering meets stated requirements such as credit-score eligibility, fees, payment terms, memberships, and card-management features.

## Scope and safety

This workflow is an informational comparison only. It must not apply for a card, enroll a customer, alter an account, disclose account data, or imply that approval is guaranteed. A credit score meeting a published threshold means only that the documented threshold is met; underwriting, income review, identity checks, and other application requirements may still apply.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Because comparison alone is not a banking action, do not request identity fields or call customer-account tools solely to answer a product-comparison question. If the request progresses to an application or another banking action, stop the comparison workflow and complete the applicable verification, eligibility, disclosures, and confirmation steps before taking that action.

## Inputs to collect from the conversation and product materials

1. Record the customer's explicit constraints, preserving units and comparators. Examples of useful normalized fields are:
   - `credit_score`
   - maximum foreign-transaction-fee percentage
   - maximum minimum-payment percentage
   - whether virtual-card management is required
   - required membership(s), or memberships the customer does not have
   - personal versus business-card preference
2. Read the supplied product documentation for each potentially relevant card. Capture the exact documented value and a source label (document title or ID) for every comparison field.
3. Do not treat a missing term as favorable. Mark it as unknown and exclude the product from a definitive recommendation unless the customer accepts the uncertainty.
4. Do not invent an income threshold, rewards condition, approval decision, or feature availability that is not documented. If income is supplied but no product material makes it an eligibility criterion, state that it was not used in the documented comparison.

Use `scripts/match_cards.py` once the facts have been structured. The script is deterministic: it evaluates documented fields only and does not make banking changes.

## Structured script interface

The script receives one JSON object on stdin and emits one JSON object on stdout.

Input schema:

- `customer` (object)
  - `credit_score` (number, optional)
  - `memberships` (array of strings, optional; use an empty list when known to be none)
- `requirements` (object)
  - `max_foreign_transaction_fee_percent` (number or percent string, optional)
  - `max_minimum_payment_percent` (number or percent string, optional)
  - `requires_virtual_card_management` (boolean, optional)
  - `product_type` (string, optional, such as `personal` or `business`)
- `cards` (array of objects). Each card requires `name` and may include:
  - `product_type`
  - `minimum_credit_score` (`0` may be used when the documentation explicitly defines it as no score requirement)
  - `foreign_transaction_fee_percent`
  - `minimum_payment_percent`
  - `virtual_card_management` (boolean)
  - `required_memberships` (array of strings)
  - `source` (source label retained in the output)

The output contains `qualified`, `not_qualified`, and `needs_review` arrays. Each entry retains the provided card fields and includes documented pass/fail/unknown reasons. `qualified` means every requested, documented criterion passed; it is not an approval result.

A shell-independent runnable invocation is:

```sh
python scripts/match_cards.py < "$INPUT_JSON_FILE"
```

where `INPUT_JSON_FILE` contains a JSON object conforming to the schema above. The executor must inspect the JSON response before drafting the customer-facing answer.

## Decision method

1. Transcribe requirements and candidate facts faithfully from the supplied material. Keep the cited source alongside each candidate.
2. Normalize percentage values as percentages, not decimal fractions: `1.5%` and `1.5` both represent 1.5 percentage points for this workflow.
3. Evaluate every explicit constraint:
   - A fee or payment percentage passes when it is less than or equal to the customer's maximum.
   - A minimum credit-score threshold passes when the supplied score is at least the documented threshold. A documented value of zero is evaluated as no positive score barrier.
   - A required virtual-card feature passes only when documentation says it is available.
   - A membership requirement passes only when the customer is known to hold that membership.
   - When a product type is requested, reject a documented different type; mark it unknown if the product type is not documented.
4. Treat a product as a match only when no requested criterion fails or is unknown. Do not select the first superficially similar product without checking all constraints.
5. If several products qualify, present all of them or ask the customer which documented trade-off matters next (for example annual fee, APR, rewards, or protection). Do not silently optimize a criterion the customer did not state.
6. If no products qualify, say so plainly, name the specific documented blockers for the relevant products, and do not suggest that exceptions can be granted.

## Customer-facing response

Give a concise conclusion first. For each recommended card, state the key matching terms, the score-eligibility finding, and its source. Clearly distinguish:

- **Meets the published criteria** from **will be approved**.
- Documented facts from information not provided in the material.
- A percentage minimum-payment term from any unprovided dollar minimum or balance-basis detail.

Mention material fees or terms that are directly relevant to the stated use case when documented, but do not overwhelm the comparison with unrelated terms. If a crypto-related use is mentioned, do not infer that a card supports crypto purchases, crypto rewards, wallet transfers, or special merchant treatment unless that specific product documentation says so.

## No-match and transfer handling

First provide the supported no-match result. If, after that unavailable-offer result, the customer demands escalation or says they will take their business elsewhere, transfer using `transfer_to_human_agents` with reason `customer_demands_after_unavailable_offer_refusal`. The summary must state the requested criteria, that the documented catalog had no confirmed match, and that no application or account action was taken. If the customer simply requests a human without a no-match escalation context, use `customer_requests_human_no_specific_reason`; use `customer_frustrated_demands_human` when the customer expresses frustration and explicitly requests human assistance.

## Validation before responding

- Every recommendation has a source and passes every stated requirement.
- Every excluded product has a concrete documented failing condition; unknown facts are labeled unknown rather than failed.
- Percentage comparators and score direction are correct.
- No approval promise, unsupported eligibility claim, or banking action is made.
- The response either offers supported matches, explains that no confirmed match exists, or requests the single missing fact needed for comparison.
