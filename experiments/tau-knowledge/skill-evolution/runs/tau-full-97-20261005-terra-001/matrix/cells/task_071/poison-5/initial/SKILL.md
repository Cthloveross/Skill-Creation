---
name: business-account-recommendation-and-opening
version: 1.0.0
description: Recommend a single business checking and/or savings account from documented product facts and stated must-haves, apply date-bounded promotional priority only among qualifying products, and safely handle a later request to open or fund an account.
---

# Business Account Recommendation and Opening

Use this skill when a customer wants a business checking or savings recommendation, possibly followed by an account-opening request. It distinguishes a product recommendation from a banking action: do not open an account, transfer funds, change a profile, or expose internal tool details merely because the customer asks which product fits.

## Inputs to collect

1. Separate checking requirements from savings requirements. Treat words such as “need,” “must,” “non-negotiable,” and “at least” as hard requirements.
2. Obtain only the customer facts necessary to evaluate product-specific eligibility. Do not assume a fact that was not supplied or verified.
3. Use the current date/time when a promotion has effective dates.
4. Use documented product facts only. An unavailable or undocumented feature is **not** evidence that a product qualifies.
5. For an opening request, collect the customer’s explicit confirmation of the exact official account class. A recommendation is not itself authorization to open an account.

## Recommendation method

1. Convert each must-have into a testable condition. Examples include a minimum daily mobile-deposit limit, an exact $0 overdraft fee, or same-day ACH availability.
2. Evaluate every documented candidate separately. A candidate qualifies only when every stated condition is supported by product evidence and any applicable product eligibility condition is satisfied.
3. If more than one candidate qualifies, apply an active promotion’s ordered priority **only to those qualifying candidates**. Check both start and end dates inclusively. Never use a promotion to override a must-have.
4. If no candidate can be confirmed as qualifying, state which required fact is missing or unmet and ask a targeted follow-up; do not guess or substitute a near match.
5. Recommend the highest-priority qualifying product, explain the specific matching features briefly, and disclose any unverified opening eligibility as a condition rather than presenting the account as already open.
6. Keep checking and savings evaluations independent. A customer may receive one recommendation for each category, but opening a savings account has additional dependency checks.

For deterministic ranking, prepare JSON from the current conversation and documented catalog facts, then run:

```sh
python3 scripts/rank_products.py < request.json
```

The script does not retrieve facts or take banking actions. It reports a recommended name only when supplied facts prove that the candidate meets every rule.

### `rank_products.py` input schema

```json
{
  "as_of": "YYYY-MM-DD or timestamp containing YYYY-MM-DD",
  "categories": {
    "category_name": {
      "customer_facts": {"fact_name": "value"},
      "requirements": [
        {"field": "product_attribute", "operator": "gte|lte|equals|is_true|exists", "value": "required for non-unary operators"}
      ],
      "products": [
        {
          "name": "official product name",
          "attributes": {"product_attribute": "value"},
          "eligibility": [
            {"field": "customer_fact", "operator": "gte|lte|equals|is_true|exists", "value": "threshold or expected value"}
          ]
        }
      ],
      "promotions": [
        {"name": "official product name", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "rank": 1}
      ]
    }
  }
}
```

`requirements` test product attributes. `eligibility` tests supplied customer facts. Supported comparison operators are `gte`, `lte`, `equals`, `is_true`, and `exists`. Do not encode an unknown value as zero or false; omit it so the result identifies it as missing. List promotions in priority order or give explicit positive `rank` values.

### Script output and validation

The script emits one JSON object to stdout:

- `ok: true` means the request format was valid.
- For each category, `recommendation` is the selected product name or `null`.
- `qualifying_products` lists all proven matches in final ranking order.
- `not_qualified` identifies unmet or missing conditions for each other candidate.
- `promotion_applied` is true only when an active promotion changed the ordering of qualifying products.

Before using the result, ensure that all customer requirements are represented in `requirements`, names match the official catalog, the `as_of` date is present for a time-limited promotion, and every field relied on has evidence. A `null` recommendation is a stop condition for that category, not permission to recommend an unproven product.

## Product facts available in this package

Use `references/product_facts.md` for the supplied business-account facts and promotion windows. These facts support a product-fit recommendation only. Do not generalize a listed fact to another product or imply a feature not documented there.

## Customer-facing response pattern

Give a concise, decision-oriented response:

- Name one recommended checking account and one recommended savings account only when each is proven to meet that category’s must-haves.
- State the matching requirements and, where applicable, that an active promotion decided the order among multiple fits.
- State material limitations or fees that are relevant to the customer’s stated needs when documented.
- Say that no account has been opened and no funds have moved unless those actions actually occurred.
- If the customer asks to proceed, obtain explicit confirmation and follow the action controls below.

## Controls before any banking action

The following control is mandatory and is preserved verbatim:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This includes opening an account and transferring an opening deposit. Recommendations alone are not banking actions, but do not represent that eligibility is complete merely because a product is a fit.

When identity verification is needed, compare two of the four identity fields (date of birth, email, phone number, and address) against the customer record. After successful verification, use the normal verification logging tool with the complete required profile fields and a current timestamp. Confirm authority and ownership before relying on any account as a source or qualifying account.

## Account-opening procedure after explicit confirmation

Use this section only after the customer asks to proceed and confirms the exact account class. Use normal banking tools; do not provide tool names, signatures, or internal implementation details to the customer.

### Business checking

Before opening, confirm all of the following:

- identity is verified;
- the customer has at least one personal checking account with status OPEN;
- the customer has no more than 6 business checking accounts;
- the customer has no account with status CLOSED;
- the existing checking account balance is at least $500; and
- the customer confirmed the desired official business checking account class.

After all controls and eligibility checks pass, use the documented account-opening capability for a checking account with the confirmed class. Confirm the resulting account to the customer without claiming any unverified benefit.

### Business savings

Before opening, confirm all of the following:

- identity is verified;
- the customer has at least one business checking account with status OPEN;
- the customer has fewer than 4 business savings accounts;
- no account has a negative balance;
- at least one OPEN business checking account has been open for at least 30 days;
- that same qualifying checking account has a current balance of at least $2,500; and
- the customer confirmed the exact official savings account class, including the “Account” suffix.

After all controls and eligibility checks pass, use the documented account-opening capability for a savings account with the confirmed class. Then ask whether the customer authorizes an opening-deposit transfer now.

- If authorized, confirm the amount, available balance, fees, limits, cutoff, source ownership, and source account. Use the checking account that meets both the 30-day and $2,500 requirements as the source. Perform the transfer only after the new savings account exists and all prerequisites are confirmed.
- If the transfer fails, inform the customer and explain that the account may be funded by internal transfer or external deposit within 30 days; otherwise it will be closed.
- If the customer does not authorize funding now, explain the same 30-day funding deadline and do not move funds.

If required account data, identity data, authority, tool access, or a customer confirmation is unavailable, stop before the action. Explain what cannot yet be verified and request the missing information or use an approved support path; never bypass a prerequisite.
