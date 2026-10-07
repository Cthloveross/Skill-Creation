---
name: evidence-backed-savings-card-recommender
description: Recommend the best documented savings-account and credit-card pairing for a customer's stated balance, time horizon, and fee constraints. Use when APY bonuses, card fees, subscriptions, account minimums, and approval eligibility must be compared without opening products or moving funds.
---

# Evidence-Backed Savings and Card Recommender

Use this Skill for an informational recommendation. Read the task-supplied product documentation and clarification record as the source of current terms. A customer asking which option is best has **not** authorized account opening, a card application, linking, or a transfer.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

An informational comparison is not a banking action. Opening an account, applying for a card, linking products, or transferring money is a banking action.

## Recommendation procedure

1. Extract the customer's current request and constraints from the conversation. In particular, distinguish:
   - maximum acceptable card annual fee;
   - whether a paid subscription is acceptable;
   - deposit amount and intended duration;
   - known balance, opening-deposit, and statement-delivery constraints; and
   - stated credit-score information.
2. Build candidates only from supplied documentation. For each viable savings/card pairing, record the savings base APY, the card's bonus for that **same savings account**, card annual fee, any required subscription cost, and all explicitly applicable conditions.
3. Exclude a candidate when it conflicts with an explicit customer constraint. A fee waiver that requires a subscription the customer declined is not a no-cost option. Do not substitute a bonus from documentation for another account.
4. Credit-card APY bonuses do not stack: use only the highest applicable documented card bonus. Apply a checking boost, relationship bonus, or direct-deposit bonus only when its documentation gives both its amount and satisfied eligibility. Do not assume that a customer has a qualifying checking product merely because they have checking.
5. Calculate a stable-balance one-year estimate as:

   `estimated interest = deposit × effective APY / 100`

   `estimated net return = estimated interest − known annual card fees − known required annual subscription costs − other known recurring costs`

   APY is already annualized; do not compound an APY a second time. For a different duration, clearly label any proration as an estimate and do not prorate a fee unless the terms support doing so. `scripts/rank_combinations.py` can perform the arithmetic after the documented facts have been supplied to its JSON input.
6. If the supplied terms and the customer's facts are sufficient, answer the final question directly in the same turn. Do **not** say that current terms are unavailable, ask the customer to supply terms already present in the task materials, or defer a recommendation merely because product opening would require later verification.

## Required recommendation content

For a recommendation about the best no-annual-fee option, the response must plainly state:

- the recommended savings account and recommended card by their official names;
- that the selected card's annual fee is $0 (or other documented no-fee wording);
- the savings base APY, the selected card's applicable APY bonus, and the resulting effective APY;
- the dollar interest/net-return estimate for the stated balance and period, including the stable-balance assumption;
- known required recurring costs and a distinction between those costs and behavior-dependent charges not included in the estimate;
- material savings-account conditions: minimum opening deposit, ongoing minimum balance, and paperless-statement requirement when documented;
- whether the stated score appears to meet a documented minimum, while making clear that approval remains subject to application and underwriting; and
- that no account, card application, linkage, or transfer has been performed. Invite the customer to explicitly select the products if they want next steps.

Use a concise calculation sentence such as: “Base APY + documented card bonus = effective APY; on the stated balance maintained for one year, that is approximately $X.” This makes the conclusion auditable.

If available terms identify one no-fee card with the highest applicable bonus for the selected savings account, recommend it rather than presenting an unnecessary list. Explain briefly why a higher bonus from a paid-fee card or paid membership was excluded. If a required term is genuinely absent, identify the missing fact and give only a conditional conclusion.

## Credit and eligibility language

A score threshold is an application eligibility screen, not an approval decision. State “appears to meet the documented minimum based on the score you provided; approval is subject to the application and underwriting.” Do not imply that a card is approved, opened, active, or linked until a supported execution tool confirms it.

## After a customer explicitly selects products

Do not begin this workflow unless the customer clearly selects a savings account and authorizes opening it. Card application requires its own explicit authorization and must use only a supported documented channel.

1. Verify identity and authority before any banking action. Verify at least two profile fields against the customer record and log verification only after those fields match.
2. Before opening savings, verify all documented prerequisites: verified identity, an active qualifying checking account, required checking tenure, fewer than the maximum permitted personal savings accounts, and no collections or negative balances. Do not infer these facts from a general recommendation.
3. Confirm the exact official savings account name, opening deposit, ongoing minimum, account fees, paperless requirement, funding choice, and final authorization.
4. Only after all prerequisites and authorization are present, use the documented savings-opening tool with the exact official account class.
5. Transfer funds only after a successful opening and separate explicit transfer authorization. Verify owned source account, available balance, amount, limits, cutoffs, and destination before transfer.
6. If the customer declines immediate funding, state the documented funding deadline and consequence. Report only tool-confirmed results.

## Calculator interface

Run `scripts/rank_combinations.py` with a JSON object on stdin and read its JSON object from stdout. It is an arithmetic aid, not a product-terms source and not authorization to act.

```json
{
  "deposit": 5000,
  "term_years": 1,
  "constraints": {
    "max_card_annual_fee": 0,
    "allow_paid_subscription": false
  },
  "combinations": [
    {
      "id": "runtime-label",
      "savings_account": "Official savings account name",
      "card": "Official card name",
      "base_apy_percent": 0,
      "card_apy_bonuses_percent": [0],
      "checking_apy_boosts_percent": [],
      "other_additive_apy_bonuses_percent": [],
      "annual_card_fee": 0,
      "annual_subscription_fee": 0,
      "other_known_annual_costs": 0,
      "notes": ["Only documented, customer-applicable facts"]
    }
  ]
}
```

The output ranks eligible combinations, lists rejected combinations and reasons, and exposes the applied highest card and checking bonuses. Before using output in a customer response, cross-check every input fact against the supplied documentation and disclose material conditions that the calculator does not model.
