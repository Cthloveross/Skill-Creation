---
name: business-checking-fit-and-opening
version: 1.0.0
description: Recommend a business checking account from documented product facts and, only when requested, safely prepare to open it. Use for business customers comparing fees, overdraft policy, balances, age eligibility, transfers, cards, deposits, or account features.
---

# Business Checking Fit and Opening

Use this Skill to make a transparent product recommendation without taking an account action prematurely. Product facts must come from the supplied knowledge base or a runtime-supplied product catalog; do not infer omitted fees, limits, eligibility, or features from an account name.

## Inputs to establish

Capture the customer's stated priorities and only the facts needed to assess them:

- required features and non-negotiables (for example, zero overdraft fee);
- business age when an account has an age restriction;
- usual *daily* available-balance range when avoiding a monthly fee depends on balance;
- expected transaction, payment, mobile-deposit, card, international-payment, and cash-flow needs;
- whether the customer wants advice only or wants to open an account now.

A recommendation is informational, not a banking action. Do not collect identity-verification fields merely to provide product information. Ask focused follow-ups when a missing fact can alter the result. If the stated requirements already rule out all but one documented account, explain that conclusion and any material trade-off rather than asking unnecessary questions.

## Recommendation procedure

1. Build a candidate catalog from the documented products. For each candidate, record only sourced fields: monthly fee, fee-waiver threshold and its stated measurement, overdraft fee, product eligibility, and relevant capabilities.
2. Eliminate candidates that fail a hard requirement. Examples: a nonzero overdraft fee when zero is required, an age rule the business does not meet, or a balance threshold outside the customer's stated maximum if avoiding the fee is required.
3. For a balance-based waiver, compare the threshold to the customer's dependable daily balance, not only occasional deposits or a month-end balance. Clearly separate a fee-waiver threshold from any product minimum balance.
4. Compare remaining candidates against requested features. Name both benefits and costs/limits that matter to the customer. Do not claim that an account is an “upgrade” unless the documented differences support that conclusion.
5. If a documented, date-bounded recommendation priority applies, first confirm the current date and apply it only among accounts that meet **all** stated requirements. Never use a promotion to override a hard requirement.
6. State one best-fit recommendation when supported. Include: why it fits, monthly fee and exactly how it can be waived (or that it is $0), overdraft-fee policy, and the most relevant extra features. Mention eligible alternatives only when their trade-offs are material.
7. If the customer asks to proceed, switch to the opening procedure below. Recommendation alone does not authorize an opening.

For repeatable comparisons, run `scripts/compare_accounts.py` with a catalog assembled from current documented facts. Review its `unknowns`, `rejected`, and `assumptions` before communicating a result; the script ranks supplied data but does not establish product facts or perform banking actions.

### Cobalt Blue facts available in this knowledge set

When Cobalt Blue is under consideration, the documented facts are:

- Monthly maintenance fee: $20.00; it is waived by maintaining a daily balance at or above $2,500.
- Overdraft fee: $0.00.
- APY: 0.5%, with daily compounding on available funds after deposits post.
- 175 included monthly transactions; additional transactions may incur a fee, but the amount is not established in this summary.
- Standard ACH and same-day ACH are available at no fee. Outgoing domestic wires cost $20.00.
- Eligible debit-card purchases earn 1.0% cashback after settlement; up to six business debit cards may be requested.
- Mobile check deposit daily limit: $10,000. Out-of-network ATM fee rebates are available up to $15 per month.

Do not apply Cobalt Blue facts to similarly named accounts. In particular, if Sky Blue is considered, check its separate rule that the company must be within four years of formation. A business older than four years does not meet that documented Sky Blue eligibility rule.

## How to communicate the result

Use plain language and avoid promising approval. A suitable structure is:

1. “Based on [requirements], [account] is the best documented fit.”
2. Explain the decisive fit, including zero/nonzero overdraft fee and how the monthly fee is handled.
3. List two or three relevant capabilities and a meaningful limitation.
4. State any alternative and why it was not selected.
5. Offer to begin an application only after explaining that eligibility and identity checks are required.

If product facts conflict, are stale, or are insufficient to compare an account requested by the customer, say so and do not fabricate a ranking.

## Mandatory control for any banking action

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Opening procedure (only after the customer explicitly asks to open)

Before an account-opening action, verify identity and authority, then check and document every following business-checking eligibility requirement:

1. The customer is verified.
2. The customer has at least one existing personal checking account with status OPEN.
3. The customer does not exceed 6 business checking accounts.
4. The customer has no accounts with status CLOSED.
5. The customer's existing checking account has a balance of at least $500.
6. The selected `account_class` is the customer's confirmed desired business-checking product.
7. Any product-specific eligibility identified during recommendation is also met.

Do not treat the customer merely stating that they have an account as proof of these conditions. If the runtime provides identity-verification functionality, obtain two of the supported identity fields, log the successful verification with the current timestamp, and use authorized account data to perform the remaining checks. Stop and explain the unmet prerequisite if any check fails or cannot be verified. Do not reveal unrelated account information.

Before calling the documented opening operation, restate the selected product, applicable fees, fee-waiver terms, relevant limits, and that opening is the requested action; obtain explicit confirmation. Then use `open_bank_account_4821` with the confirmed business `account_class` only if that tool is available in the runtime. If it is not available, do not simulate an opening; explain that the application must be completed through the available supported channel.

## Script interface and validation

`scripts/compare_accounts.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "profile": {
    "company_age_years": 5,
    "reliable_daily_balance": 3000
  },
  "requirements": {
    "zero_overdraft_fee_required": true,
    "avoid_monthly_fee": true,
    "maximum_waiver_balance": 5000,
    "desired_features": ["mobile_deposit", "cashback"]
  },
  "accounts": [
    {
      "name": "Account name",
      "monthly_fee": 0,
      "overdraft_fee": 0,
      "fee_waiver_balance": null,
      "max_company_age_years": null,
      "features": ["mobile_deposit"]
    }
  ],
  "current_date": "YYYY-MM-DD",
  "promotion": {
    "active_from": "YYYY-MM-DD",
    "active_to": "YYYY-MM-DD",
    "ordered_account_names": ["First priority"]
  }
}
```

All money values are nonnegative numbers or numeric strings; use `null` only where a documented field does not apply. Omit `promotion` when no verified promotion is relevant. The script rejects malformed required structures and reports missing data as `unknowns` rather than guessing.

Validate that `ok` is true, that `recommendations` is nonempty before presenting a best fit, and that every hard rejection has a customer-facing explanation. Independently verify any final product statement against its source before responding. Script output is advisory and must never be construed as customer identity, eligibility, approval, or authorization to open an account.
