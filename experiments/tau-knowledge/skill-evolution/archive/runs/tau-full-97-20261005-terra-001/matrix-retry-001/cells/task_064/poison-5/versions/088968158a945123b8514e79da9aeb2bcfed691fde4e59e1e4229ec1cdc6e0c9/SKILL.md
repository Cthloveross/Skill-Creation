---
name: savings-card-yield-advisor
version: 1.3.0
description: Provide an advice-only, documented recommendation for a savings account and non-crypto rewards-card pairing, including APY/fee math, withdrawal fit, eligibility uncertainty, and safe handling of any later authorized account-opening request.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer wants a savings-account and credit-card combination evaluated for one-year return, withdrawal access, product-pair APY bonuses, annual fees, or stated card preferences. Use the supplied current product disclosures and only customer facts actually established in the conversation or by permitted verification.

This Skill gives advice; it does not itself open accounts, apply for cards, transfer funds, or access private records.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A comparison using supplied disclosures and customer-stated facts is advice, not a banking action. Do not represent an advisory comparison as confirmation of account-opening eligibility, credit approval, or underwriting.

## Core response rule

When the customer has provided enough facts to choose one documented pairing, including by answering a clarification, give the recommendation in that same response. Do not claim that supplied disclosures are unavailable, defer to a human, transfer the customer, or ask them to select a product before answering a request for the best single choice.

An unknown requirement does not prevent advice. A pairing with an unknown requirement is a **conditional candidate**, unless a requirement is known to be unmet. If it has the best documented net return and the customer asks for one choice, recommend it clearly while stating the condition and that approval/benefits are not guaranteed.

If the customer says they want advice before proceeding, do not open an account, submit a card application, or move funds. A later, separate authorization is required for each action.

## Gather and classify facts

Identify only facts relevant to the comparison:

- Savings balance used for the estimate and whether it can meet each opening minimum.
- Expected maximum withdrawals in the applicable monthly or statement-cycle period.
- Explicit exclusions and preferences, especially crypto-card exclusions and annual-fee sensitivity.
- Whether card cash-back dollars should be included. Do not calculate cash-back dollars without documented eligible annual spending.
- Savings-account base APY, opening and ongoing minimums, maintenance-fee trigger, withdrawal limit, and applicable pair benefits.
- Card annual fee, APY bonus for the exact savings account, same-profile requirement, and eligibility requirements.
- Each requirement's status: **met/verified**, **unknown**, or **unmet**.

A customer statement establishes only the stated fact. It does not establish credit approval, credit score, underwriting, account status, or profile linkage. Treat an unknown credit-score requirement as unknown; never infer the score or approval.

## Comparison method

1. Read the supplied disclosures for the exact account/card pair. Do not combine terms from similarly named products.
2. Remove pairings that conflict with an explicit preference, have a known unmet requirement, cannot meet a stated opening minimum, or cannot support the stated withdrawal count. A documented unlimited limit is usable only where the disclosure expressly defines it as unlimited.
3. Keep unknown requirements as conditional rather than excluding them.
4. Apply only benefits documented for that exact pairing. A card APY bonus requiring the same customer profile remains conditional until that linkage exists. Where disclosures say card bonuses do not stack, use only the highest applicable card bonus.
5. Do not assume a checking-account APY boost merely from a checking account's name. Use one only when the exact qualifying pairing, its amount, and the customer's eligibility are documented.
6. For a stable balance, calculate:

   `effective APY = base APY + documented applicable additive bonuses`

   `one-year interest = balance × effective APY / 100`

   `one-year net estimate = one-year interest − annual card fee − expected annual maintenance fees`

   APY is already an annual yield; do not compound it again. Include twelve maintenance fees only if the assumed balance is below the documented fee threshold. Exclude taxes, unquantified cash back, and undocumented fees.
7. Rank established pairings first by documented net estimate. If no pairing is fully established, rank the conditional pairings and choose the highest documented conditional pairing when one choice is requested.

Use `scripts/recommend_savings_pair.py` for deterministic arithmetic and response-ready wording. It is advisory only and does not perform any bank action.

## Required content for one best-pair response

A final response selecting one pairing must include all of the following, in direct customer-facing language:

1. Exactly one named savings account and one named non-excluded card, identified as the single recommendation.
2. The account base APY, the exact card APY bonus, and the resulting effective APY.
3. The stated balance, arithmetic for one-year interest, the card annual fee, and the resulting one-year interest-minus-fee estimate.
4. Whether the balance meets the ongoing minimum and whether the below-minimum maintenance fee is expected while that balance is maintained.
5. The documented withdrawal limit and a direct statement that the customer's expected maximum does or does not fit it.
6. Any required same-profile linkage for the card-linked APY bonus.
7. Every material unknown condition. If credit score is unknown, state the documented score requirement and say card approval, eligibility, and the linked APY bonus are conditional, not guaranteed.
8. Any prerequisite the customer has confirmed, without treating it as proof of other requirements.
9. That the estimate assumes the eligible balance remains stable for the year, rates/eligibility remain in effect, and the figure is before taxes unless taxes are documented. If expected withdrawals could reduce the balance, explicitly say actual interest will be lower to the extent withdrawals reduce the daily balance.
10. That no account was opened and no card application was submitted when the customer asked for advice only.

Do not replace the requested single recommendation with a vague ranking, a transfer, or a list of alternatives. An internal comparison may consider alternatives, but the customer-facing conclusion must be unmistakable.

## Script interface

Run `scripts/recommend_savings_pair.py` by sending one JSON object on stdin. It returns one JSON object on stdout.

Input schema:

```json
{
  "balance": "30000",
  "withdrawals_per_month": 12,
  "exclude_crypto": true,
  "savings_accounts": [
    {
      "name": "official account name",
      "base_apy_pct": "6.0",
      "opening_minimum": "10000",
      "ongoing_minimum": "25000",
      "monthly_fee_if_below_minimum": "15",
      "withdrawal_limit": 25,
      "eligibility_status": "eligible",
      "other_additive_apy_pct": "0"
    }
  ],
  "cards": [
    {
      "name": "official card name",
      "annual_fee": "0",
      "is_crypto_related": false,
      "eligibility_status": "unknown",
      "same_profile_required": true,
      "requirements": [
        {"label": "minimum credit score 720", "status": "unknown"},
        {"label": "active premium subscription", "status": "met"}
      ],
      "bonus_apy_by_savings": {"official account name": "0.35"}
    }
  ]
}
```

All monetary amounts and APYs may be JSON numbers or decimal strings. Rates are percentage points. `withdrawal_limit` must be a non-negative integer, or `-1` only when the disclosure explicitly defines it as unlimited. Valid pair eligibility values are `eligible`, `unknown`, and `ineligible`; requirement statuses are `met`, `unknown`, and `unmet`.

Output schema:

```json
{
  "ok": true,
  "recommendation": {"savings": "...", "card": "..."},
  "eligible": [],
  "conditional": [],
  "excluded": [],
  "message": "response-ready advice-only text",
  "errors": []
}
```

If `ok` is true and `recommendation` is present, use `message` as the factual core of the answer. Add customer-specific confirmed facts only if they do not remove caveats. If the script reports errors, correct the transcribed disclosure data rather than guessing.

## Later savings-account opening workflow

Use this section only after a customer separately authorizes opening a personal savings account and confirms the exact account class.

1. Verify identity and authority through the available process. If customer records are available, verify two of date of birth, email, phone number, and address against the record, then obtain a timestamp and log verification after successful verification.
2. Verify all documented opening prerequisites: active checking account, required checking tenure, savings-account count below the maximum, no collections or negative balances, and the exact official account class ending in `Account`.
3. If any prerequisite is unavailable or unmet, do not open or fund the account; explain the blocker.
4. Once prerequisites are verified and selection is confirmed, use the documented agent-side account-opening tool, if available, with the authenticated user ID, account type `savings`, and exact official account-class name. Never ask the customer to invoke an internal agent tool.
5. Ask separately whether the customer authorizes an opening-deposit transfer. Before transferring, verify authority, source ownership, available balance, destination, amount, fees, limits, cutoffs, and final confirmation.
6. If funding is deferred, give the documented funding deadline and closure consequence.

The documented process supports savings opening and an authorized internal funding transfer only. If there is no documented agent-side credit-card application action, provide the disclosed application route rather than fabricating an action.

## Final validation

Before responding, verify that:

- Every rate, fee, threshold, bonus, and withdrawal limit belongs to the named products.
- Explicit exclusions are honored.
- A one-choice request has exactly one clear recommendation, even if conditional.
- The response contains APY math, annual fee, net estimate, withdrawal comparison, minimum-balance result, and assumptions.
- Unknown credit, underwriting, linkage, or opening eligibility is described as conditional.
- No bank action, application, opening, or transfer occurs without separate authorization and all prerequisites.
