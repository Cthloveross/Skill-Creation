---
name: savings-card-yield-advisor
version: 1.2.0
description: Compare documented savings accounts with non-crypto rewards cards, calculate a one-year interest-minus-annual-fee estimate, explain withdrawal capacity and conditional eligibility, and safely handle a separately authorized savings-account opening.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer asks which savings account and credit-card pairing best supports their balance, withdrawal needs, and return objective; asks for a documented APY pairing benefit; or separately asks to open a personal savings account. Use current supplied disclosures and customer-stated facts. Do not invent product terms, personal eligibility, underwriting results, or account status.

This Skill provides advice and calculations. It does not submit a credit-card application, open an account, or move money unless the customer separately authorizes the applicable action and every required banking prerequisite has been verified.

## Banking control — mandatory

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Apply this control before opening an account, transferring an opening deposit, accessing non-public customer information, changing a profile, or taking any other banking action. A recommendation based only on supplied product disclosures and customer-stated facts is not a banking action. Do not imply that an advisory comparison confirms personal eligibility.

## Respond when the recommendation is ready

When the customer has supplied enough information to answer a request for one best combination—including through a reply to a clarification—give the recommendation in that same response. Do **not** defer the answer for more research, claim the disclosures are unavailable when supplied disclosures contain the terms, transfer the customer, or ask the customer to choose between products before providing the requested ranking.

An unknown approval criterion does not make a documented comparison unavailable. Keep a product with an unknown requirement as a **conditional** candidate. If it is the best documented fit and the customer asks for one choice, name it as the single recommendation and clearly state what remains conditional.

For an advice-only request, do not open an account, transfer funds, submit a card application, or imply that an application has started. A later, separate authorization is required to proceed.

## Information to identify

Identify only the facts needed for the request:

1. Stable savings balance assumption, ability to meet the opening deposit, and whether the balance is expected to remain above the ongoing minimum.
2. The maximum expected withdrawals in the documented monthly or statement-cycle period. Distinguish a withdrawal limit from a limit on *free* withdrawals.
3. Explicit preferences and exclusions, including exclusion of crypto-related cards and annual-fee tolerance.
4. Expected eligible card spending only if the customer asks to include cash-back dollars. Do not convert a cash-back percentage into annual dollars without documented qualifying spending volume.
5. Each relevant card or account requirement, labelled as **met/verified**, **unknown**, or **unmet**. Never infer a credit score, underwriting approval, subscription, profile linkage, or opening eligibility.
6. Whether the customer wants advice only or separately authorizes account opening and, subsequently, an opening-deposit transfer.

Customer statements can establish only the fact stated by the customer; they do not establish underwriting approval. Use the current date only when evaluating a promotion with documented dates.

## Comparison and calculation method

1. Read the supplied disclosures for each relevant savings account and eligible traditional-rewards card. Extract the exact base APY, opening and ongoing minimums, fee trigger and fee, withdrawal limit, card annual fee, card-specific APY bonus, requirements, and same-profile linkage requirement.
2. Exclude a card that violates an explicit preference, such as a crypto-card exclusion. Exclude a pairing when the stated balance cannot meet its documented opening minimum, its withdrawal limit cannot support the stated maximum, or a requirement is known to be unmet.
3. Do not exclude a pairing merely because credit score, approval, or another requirement is unknown. It remains conditional.
4. Apply only benefits documented for that exact savings account and card. When more than one card bonus applies, use only the highest applicable card bonus; card bonuses do not stack. Do not assume a checking-account boost from a similarly named checking account. Use a checking boost only if the exact documented pairing and customer eligibility are established.
5. For a stable balance, calculate:

   `effective APY = base APY + applicable documented additive bonuses`

   `one-year interest = balance × effective APY / 100`

   `one-year net estimate = one-year interest − annual card fee − expected annual maintenance fees`

   A quoted APY is already an annual yield; do not compound the APY a second time. Include twelve monthly maintenance fees only when the stable-balance assumption is below the fee threshold. Exclude taxes, cash back without spending data, and unprovided transaction fees.
6. Use `scripts/recommend_savings_pair.py` for repeatable ranking, arithmetic, and a response-ready explanation. The script is advisory only: it neither accesses customer information nor performs a bank action.
7. Rank fully established eligible pairings by documented one-year net estimate. If none is fully established, rank conditional pairings and select the highest documented conditional pairing when the customer requests one best choice.

If supplied disclosures materially conflict, identify the conflicting term. Do not take a banking action based on a disputed term. For advice, use a current authoritative disclosure when available and describe any unresolved conflict.

## Required single-recommendation response

For a request for one best combination, the final customer-facing response must directly include all of the following:

1. One named savings account and one named non-excluded card, introduced as the single recommendation.
2. The savings base APY, applicable card APY bonus, and resulting effective APY.
3. The calculation using the stated balance, the card's annual fee, and the resulting one-year interest-minus-annual-fee estimate.
4. Whether the stated balance meets the ongoing minimum and whether the below-minimum maintenance fee is expected while that balance is maintained.
5. The documented withdrawal limit in the applicable period and a direct comparison to the customer's expected maximum.
6. The same-profile linkage condition for the APY bonus, if documented.
7. Every material unknown requirement. For an unknown credit-score requirement, state the required score (or describe it as a credit-score requirement if the disclosure does not give a value) and say explicitly that card approval, eligibility, and the card-linked APY bonus are conditional—not guaranteed.
8. The customer facts that are established, such as a confirmed subscription, without overstating what they prove.
9. The assumptions that the balance stays stable for one year, documented rates and eligibility remain in effect, and the result is before taxes unless taxes are documented.
10. A clear statement that no account was opened and no application was submitted because the response is a recommendation only.

Do not dilute a single recommendation into a list of alternatives. A comparison may be used internally, but the requested final choice must be unmistakable.

## Using the calculation helper

Invoke `scripts/recommend_savings_pair.py` with terms transcribed from the current supplied disclosures. It reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "balance": "decimal",
  "withdrawals_per_month": 0,
  "exclude_crypto": true,
  "savings_accounts": [
    {
      "name": "official savings name",
      "base_apy_pct": "decimal percentage",
      "opening_minimum": "decimal",
      "ongoing_minimum": "decimal",
      "monthly_fee_if_below_minimum": "decimal",
      "withdrawal_limit": 0,
      "eligibility_status": "eligible|unknown|ineligible",
      "other_additive_apy_pct": "decimal percentage"
    }
  ],
  "cards": [
    {
      "name": "official card name",
      "annual_fee": "decimal",
      "is_crypto_related": false,
      "eligibility_status": "eligible|unknown|ineligible",
      "same_profile_required": true,
      "requirements": [
        {"label": "documented requirement", "status": "met|unknown|unmet"}
      ],
      "bonus_apy_by_savings": {"official savings name": "decimal percentage"}
    }
  ]
}
```

`withdrawal_limit` may be `-1` only if the supplied disclosure explicitly defines it as unlimited. `other_additive_apy_pct` defaults to zero and must only contain a separately documented, applicable additive bonus. Requirement labels should preserve meaningful conditions, such as a stated credit-score threshold or active subscription requirement.

Output schema:

```json
{
  "ok": true,
  "recommendation": {"...": "selected pairing and computed fields"},
  "eligible": ["fully established pairings"],
  "conditional": ["pairings with unknown requirements"],
  "excluded": [{"savings": "...", "card": "...", "reasons": ["..."]}],
  "message": "response-ready recommendation text",
  "errors": []
}
```

If `ok` is true and `recommendation` is present, use `message` as the factual core of the response. Add only customer-specific established facts or a concise next-step question; do not remove conditionality, fees, withdrawal comparison, linkage, assumptions, or the no-action statement. If errors are returned, correct the extracted terms from the disclosures rather than guessing.

## Withdrawal handling

Compare the customer’s maximum anticipated count to the documented limit in the same period. If it fits, say so explicitly. Do not call withdrawals free unless the disclosure says the relevant limit is free. State any documented consequence for exceeding the limit. Treat an unlimited marker as unlimited only where the supplied disclosure defines it that way.

## Savings-account opening workflow

Use this section only after the customer separately asks to open a personal savings account and confirms the exact account class.

1. Verify identity and authority through the available process. Where customer records are available, confirm two of the four identity fields—date of birth, email, phone number, and address—against the record. Obtain a timestamp and create the verification audit record only after successful verification.
2. Verify all documented prerequisites: active checking account, required checking tenure, fewer than the maximum permitted personal savings accounts, no collections or negative balances, and the exact official account class ending in `Account`.
3. If any prerequisite is unmet or cannot be verified, do not open or fund the account. Explain the unresolved requirement.
4. After all prerequisites are met and the selection is confirmed, use the documented internal account-opening tool, if available, with the authenticated customer ID, account type `savings`, and the exact official account class. Do not ask a customer to run an internal agent tool.
5. Ask separately for authorization to transfer an opening deposit. Before a transfer, verify authority, source ownership, available balance, destination, amount, fees, limits, cutoffs, and final confirmation. Transfer only after account creation and these checks.
6. If funding is deferred, state the documented funding deadline and closure consequence, then confirm account and funding status.

The documented workflow supports savings opening and an authorized internal funding transfer. If no agent-side card-application action is documented, provide the disclosed customer application path instead of fabricating an application action.

## Validation checklist

Before responding or acting, confirm:

- The product names, rates, bonuses, fees, thresholds, and withdrawal limits all belong to the named products.
- The recommendation honors stated exclusions.
- A request for one choice receives exactly one named recommendation, even when conditional.
- The response states base APY, bonus, effective APY, annual fee, calculation, and net estimate.
- The response directly addresses the stated maximum withdrawal count.
- Unknown credit, underwriting, linkage, or account eligibility is described as conditional.
- No opening, transfer, or card-application action occurs without separate authorization and all banking checks.
