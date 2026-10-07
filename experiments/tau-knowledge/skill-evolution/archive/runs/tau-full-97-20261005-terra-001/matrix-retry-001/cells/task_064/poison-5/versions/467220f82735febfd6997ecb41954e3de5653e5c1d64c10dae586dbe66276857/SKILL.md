---
name: savings-card-yield-advisor
version: 1.4.0
description: Give a documented, advice-only recommendation for one savings-account and non-crypto rewards-card pairing, including withdrawal fit, APY and annual-fee math, and clearly conditional eligibility language.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer asks which savings account and credit card combination best maximizes a stated one-year return, needs a savings withdrawal-limit comparison, or wants documented card-linked APY benefits evaluated. Use the supplied product disclosures and facts established in the conversation.

This Skill provides advice only. It does not open an account, apply for a card, transfer funds, or access private records.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A product comparison based on supplied disclosures is not a banking action. Do not describe advice as approval, verified opening eligibility, or an underwriting decision.

## Advice-first rule

When the customer asks for one best combination and the supplied disclosures contain enough terms to evaluate it, give the recommendation in the same response. Do **not** say the supplied disclosures are unavailable, transfer the customer, or ask the customer to choose a product before answering.

Use a conditional recommendation when it is the highest documented option but one or more requirements are unknown. Unknown eligibility is not a reason to withhold advice. Exclude a product only if a requirement is known to be unmet, it violates an explicit preference, it cannot meet the stated opening amount, or its documented withdrawal limit cannot support the stated usage.

If the customer asks for advice before proceeding, do not open products, submit a card application, or move money. A later, separate authorization is required for every such action.

## Gather the comparison facts

Identify and classify only relevant facts:

- Savings balance for the estimate, expected maximum withdrawals per month, and stated time horizon.
- Explicit exclusions, such as a request to exclude crypto-related cards.
- Savings base APY, opening minimum, ongoing minimum, maintenance-fee trigger, and withdrawal limit.
- Exact card annual fee and exact APY bonus for the specific savings account.
- Whether a card-linked benefit requires both products under the same customer profile.
- Card eligibility requirements and each status: **met**, **unknown**, or **unmet**.
- Whether the customer has documented annual purchase spending. Do not estimate cash-back dollars without it.

A customer statement verifies only the fact they state. It does not prove a credit score, underwriting result, card approval, account-opening eligibility, or same-profile linkage. Treat any unknown credit-score requirement as unknown.

## Comparison and calculation method

1. Read the disclosures for the exact named savings account and card. Do not combine terms from similarly named products.
2. Honor explicit exclusions. Do not recommend a crypto-related card after the customer excludes crypto.
3. Reject pairings with known unmet requirements, insufficient opening funds, or inadequate documented withdrawal access. Keep otherwise suitable pairings with unknown requirements as conditional candidates.
4. Apply only benefits documented for the exact account/card pair. If a benefit requires same-profile linkage and linkage is not established, include that as a condition for receiving the benefit.
5. Where card bonuses do not stack, use only the highest applicable card bonus. Do not infer a checking-account boost merely from the name of a checking account; use one only if the exact qualifying pair, amount, and eligibility are documented.
6. For a stable eligible balance, use:

   `effective APY = base APY + documented applicable additive bonuses`

   `one-year interest = balance × effective APY / 100`

   `one-year net estimate = one-year interest − annual card fee − expected annual maintenance fees`

   APY is already annualized; do not compound it again. Include twelve maintenance fees only when the stated assumed balance is below the documented fee threshold. Exclude taxes, undocumented costs, and unquantified card cash back.
7. Rank non-conditional candidates by documented net estimate. If all viable candidates are conditional, select the highest-net conditional candidate when the customer asked for one choice.

Use `scripts/recommend_savings_pair.py` for repeatable calculations after transcribing current disclosed values. The script is advisory and cannot perform banking actions.

## Required content in a one-choice response

The final customer-facing answer must directly include:

1. One unmistakable recommendation naming exactly one savings account and one non-excluded card.
2. The savings base APY, the exact card-linked APY bonus, and the resulting effective APY.
3. The arithmetic using the stated balance, estimated one-year interest, the card annual fee, and the resulting interest-minus-fee estimate.
4. Whether the balance meets the ongoing minimum and whether a below-minimum maintenance fee is expected while that balance is maintained.
5. The documented withdrawal limit and a direct comparison showing whether the customer's expected withdrawals fit.
6. The same-profile linkage condition when the APY bonus requires it.
7. Every material uncertainty. State an unknown minimum credit score explicitly and say approval, eligibility, and a card-linked bonus are conditional rather than guaranteed.
8. Any prerequisite the customer confirmed, while making clear that it does not establish other prerequisites.
9. The assumptions that the eligible balance remains stable for the year and rates/eligibility remain in effect, that the estimate is before taxes, and that interest falls if withdrawals reduce the daily balance.
10. If the request was advice only, state that no account was opened and no card application was submitted.

Do not replace this response with a vague ranking, a referral, a transfer, or a list of alternatives.

## Immediate-response checklist

Before sending advice, check the draft for all of these literal content categories:

- both official product names;
- the withdrawal-limit number and the customer's expected withdrawal count;
- base APY, bonus APY, effective APY, balance, one-year interest, annual fee, and net estimate;
- ongoing-minimum and maintenance-fee conclusion;
- same-profile condition when applicable;
- the actual credit-score threshold when score is unknown, plus words such as “conditional” or “approval”; and
- no assertion that an account was opened or a card was approved.

## Script interface

Run `scripts/recommend_savings_pair.py` with one JSON object on stdin. It writes one JSON object to stdout.

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
      "same_profile_status": "unknown",
      "requirements": [
        {"label": "minimum credit score 720", "status": "unknown"},
        {"label": "active premium subscription", "status": "met"}
      ],
      "bonus_apy_by_savings": {"official account name": "0.35"}
    }
  ]
}
```

Amounts and APYs may be numbers or decimal strings; APYs are percentage points. Pair eligibility is `eligible`, `unknown`, or `ineligible`. Requirement and same-profile statuses are `met`, `unknown`, or `unmet`. `withdrawal_limit` is a non-negative integer, or `-1` only if the disclosure expressly defines it as unlimited.

The output includes `recommendation`, ranked `eligible` and `conditional` candidates, exclusions, and a response-ready `message`. If `ok` is false, correct the disclosure transcription rather than guessing.

## Later savings-account opening workflow

Use this workflow only after the customer separately authorizes opening a personal savings account and confirms the exact official account class.

1. Verify identity and authority through the available process. Where customer records are available, verify two of date of birth, email, phone number, and address against the record; obtain a timestamp and log verification after success.
2. Verify all documented opening prerequisites: active checking account, required checking tenure, savings-account count below the maximum, no collections or negative balances, and the exact account class ending in `Account`.
3. If any prerequisite is unavailable or unmet, do not open or fund the account; explain the blocker.
4. After eligibility and selection are confirmed, use the documented agent-side savings-opening tool if available. Never ask the customer to invoke an internal agent tool.
5. Obtain separate authorization for any opening-deposit transfer. Before transfer, verify authority, ownership, available balance, destination, amount, fees, limits, cutoffs, and final confirmation.
6. If funding is deferred, provide the documented funding deadline and closure consequence.

The documented process supports savings opening and an authorized internal funding transfer only. If no agent-side card-application tool is documented, provide the disclosed application route rather than inventing an action.

## Final validation

Before responding, verify that every rate, fee, threshold, bonus, and withdrawal limit belongs to the named products; explicit exclusions are honored; unknown underwriting and linkage conditions remain conditional; and no account opening, application, or transfer is performed without separate authorization and all required prerequisites.
