---
name: business-checking-recommendation
version: 1.0.0
description: Recommend a business checking account from supplied product evidence and customer requirements, apply active promotional priority only among qualifying accounts, and safely prepare—not execute—an account-opening workflow.
---

# Business Checking Recommendation

Use this Skill when a customer wants help selecting or upgrading a business checking account. It produces an evidence-based recommendation, keeps non-negotiable requirements separate from preferences, and prevents an opening action before consent and eligibility checks.

## Inputs to collect

Use only current, product-specific evidence and the current conversation. Build the script input from:

- **Customer hard requirements:** monthly-fee cap, whether a zero overdraft fee is required, business age or other eligibility facts, and any required features.
- **Customer financial context:** typical *minimum* balance as well as typical range. A fee waiver that requires a daily balance is not guaranteed by an average balance.
- **Preferences:** desired payment, deposit, ATM, international, rewards, interest, transfer-limit, and team-access features. Do not treat an unstated preference as a hard requirement.
- **Candidate facts:** each account's recurring fee, waiver threshold and basis, overdraft-fee policy, eligibility rules, relevant features, and source citations.
- **Promotion facts:** promotion effective dates and ordered account priorities, if supplied.
- **Opening facts:** only after the customer explicitly asks to proceed, populate the opening-checklist fields from verified account records.

Do not mix terms from different account classes. In particular, a fee, overdraft policy, transfer limit, or eligibility rule for one account is not evidence for another account. Never infer that “optional overdraft settings” means the account has a zero overdraft fee; a zero-fee requirement needs explicit supporting evidence.

## Decision procedure

1. Convert the customer’s statements into explicit hard constraints and preferences. Preserve uncertainty rather than inventing a value.
2. For each candidate, assess:
   - whether its published monthly fee is within the cap both with and without a waiver;
   - whether the stated minimum balance supports a waiver, including its required balance basis;
   - whether its overdraft fee is explicitly zero when that is non-negotiable; and
   - each eligibility condition against the known customer facts.
3. Reject a candidate with a known hard-constraint or eligibility failure. Mark missing critical facts as **conditional**, not as qualifying.
4. Apply a currently active promotional ordering only to candidates that meet every known hard requirement and have no unresolved eligibility condition. A promotion never overrides a customer requirement.
5. Among remaining candidates, compare the features the customer actually requested and the recurring cost. If no candidate is fully supported, say what is missing or incompatible and ask the minimum necessary follow-up question.
6. Compare the recommendation with the customer’s current account only on documented facts. Do not claim an upgrade is better in an unspecified way.

Use `scripts/recommend_business_checking.py` for deterministic filtering, fee-waiver assessment, promotion ordering, and opening-readiness reporting. The script does not make bank changes.

### Script interface

The script reads one JSON object from stdin and writes one JSON object to stdout. It uses only the Python standard library.

Required top-level input:

- `customer` (object): customer facts and requirements. Supported keys include `max_monthly_fee`, `typical_balance_min`, `zero_overdraft_fee_required`, `desired_features`, and any keys referenced by eligibility rules.
- `candidates` (array): product records. Each record needs `name` and may include `monthly_fee`, `waiver` (`threshold`, `balance_basis`), `overdraft_fee`, `eligibility`, `features`, and `sources`.

Optional top-level input:

- `as_of` (ISO date or timestamp) and `promotions` (each with `start`, `end`, and ordered `priority` account names).
- `opening_intent` (boolean) and `opening_checklist` (object) after the customer has asked to open an account.

An eligibility item has `field`, `operator`, `value`, and optional `label`. Supported operators are `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, and `not_in`. The script returns rejected candidates, conditional candidates, eligible candidates in recommendation order, fee assessments, and `opening_readiness`.

Run it through the packaged-script runtime, or equivalently:

```sh
printf '%s' "$INPUT_JSON" | python3 scripts/recommend_business_checking.py
```

Validate before relying on the result:

- `errors` must be empty.
- Each claimed hard requirement must appear in the candidate’s `hard_requirements` result as `met`.
- The chosen candidate must be in `eligible_candidates`, not `conditional_candidates` or `rejected_candidates`.
- For a waiver claim, check `fee_assessment.waiver_supported_by_stated_minimum` and state the balance condition exactly.
- If a promotion was used, verify `active_promotions` is nonempty and the candidate has a numeric `promotion_rank`.

## Customer-facing response

Give a direct recommendation first, followed by a short explanation tied to the customer’s requirements:

- identify the recommended account and the documented features that make it fit;
- state the monthly fee and whether the customer’s stated minimum balance would waive it, including any daily-balance condition;
- directly address the zero-overdraft-fee requirement using only explicit evidence;
- briefly explain known exclusions or why a promotion does not change the result; and
- distinguish confirmed facts from conditions that still need verification.

Do not expose internal implementation details, account-record prerequisites, or promotional directives unless they materially explain the recommendation. Do not promise a waiver, approval, or account opening.

## If the customer wants to open the recommended account

A recommendation is not authorization to open an account. First obtain clear confirmation of the desired account class. Then follow the documented business-checking opening controls:

1. Verify the customer’s identity by confirming two of the four identity fields (date of birth, email, phone number, address).
2. Obtain the current time and log the completed verification using `log_verification` with all required fields.
3. Confirm all opening prerequisites from authoritative account records: verified customer status; at least one OPEN personal checking account; no more than six business checking accounts; no accounts with CLOSED status; and an existing checking balance of at least $500.
4. Confirm the selected `account_class` again.
5. Only when all requirements are confirmed and the customer has requested the opening, unlock and use the normal banking workflow for `open_bank_account_4821` with the required runtime arguments.

If any prerequisite is unknown or fails, do not attempt an opening. Explain the unmet or unverified requirement and offer to continue once it is resolved. Do not close or alter the customer’s existing account unless they separately request that action and its independent procedure is satisfied.

## Failure handling

- If product evidence does not explicitly state a required fee or eligibility condition, present that candidate as conditional or exclude it; do not guess.
- If no product meets all hard requirements, say so plainly and identify the conflict.
- If requirements are insufficient to differentiate otherwise suitable products, ask focused questions about the features that would change the choice.
- If the customer requests a human after the available recommendation or opening workflow cannot meet the request, use the applicable transfer path and summarize what was established.
