---
name: evidence-backed-savings-card-recommender
description: Give a complete, evidence-backed advisory recommendation for a savings account and credit-card pairing using the product terms and customer facts supplied in the current task. Use when a customer asks to maximize savings yield or net return subject to card fees, subscription preferences, balance requirements, and credit eligibility. Do not use this Skill to take banking actions unless the customer separately and explicitly authorizes them.
---

# Evidence-Backed Savings and Card Recommender

Use the supplied product documentation, clarification history, and read-only observations as the source of truth for the current recommendation. The purpose is to answer the customer's latest recommendation question, not to explain how an answer might later be obtained.

## Mandatory response rule

If the supplied facts and terms are sufficient to identify a best pairing, answer with that pairing in the current customer-facing message.

- Do **not** say that terms are unavailable when relevant terms are supplied in the task context.
- Do **not** give only a comparison plan, generic capability statement, request for facts already supplied, or human-agent transfer.
- If the customer asks for one best option, provide one best documented option rather than a menu.
- Do not let a discussion of an excluded paid option replace the requested no-fee recommendation.
- An advice request is not authorization to open an account, apply for a card, link products, or move money.

## Evidence and selection method

1. Read the latest customer request and all prior clarifications. Treat an expressed balance, time horizon, maximum annual-card-fee preference, subscription refusal, stated credit score, and request for a single answer as binding constraints.
2. Extract only current, documented facts for each supportable pairing:
   - official savings-account and card names;
   - savings base APY;
   - the card's APY bonus specifically documented for that savings account;
   - card annual fee and any required subscription cost;
   - credit-score threshold and other stated eligibility conditions;
   - opening-deposit minimum, ongoing minimum balance, statement-delivery requirement, and material transaction limits; and
   - conditions needed to retain a bonus, such as good standing or linking under the same profile.
3. Exclude a candidate that conflicts with a binding preference. A card with an annual fee is not a no-annual-fee answer. A pairing requiring a paid membership is not an answer if the customer rejected a paid membership.
4. Apply bonuses only where the documentation ties them to the recommended savings account and the customer's scenario. Do not infer an APY boost from a similarly named product or an incomplete document.
5. Where the terms state that card bonuses do not stack, use only the highest applicable card bonus. Never add card bonuses together. Do not add a checking, relationship, direct-deposit, tier, or promotional boost unless both its amount and applicability to this customer are documented.
6. Calculate the stable-balance estimate as:

   `effective APY = base APY + documented applicable additive bonuses`

   `one-year interest = balance × effective APY / 100`

   `net return = interest − known annual card fees − known required annual subscription fees − other known recurring costs`

   APY already represents an annualized yield; do not compound APY again. Do not deduct a contingent withdrawal, foreign-transaction, late-payment, or maintenance charge unless the stated scenario makes it applicable.
7. Recommend the eligible candidate with the highest supported net return. If a material fact is truly absent, identify the specific missing fact and give the strongest conditional conclusion possible; do not falsely say all terms are unavailable.

Use `scripts/rank_combinations.py` for deterministic arithmetic/ranking when useful. The script ranks evidence-grounded inputs only; it does not discover terms, determine eligibility, or authorize actions.

## Required customer-facing answer

Before responding, ensure the message includes every applicable item below in clear prose. Give the recommendation first.

1. **Recommendation.** State the official savings-account name and the official card name, tied to the stated balance, period, and fee/subscription constraint.
2. **Calculation.** State the base APY, the applicable card bonus, the resulting effective APY, and the approximate interest for the customer's balance and period. State net return after known recurring costs. If all known recurring costs are zero, clearly say the gross interest and net return are the same under the stated assumptions.
3. **Card cost and apparent eligibility.** Explicitly state the selected card's annual fee, including "$0 annual fee" when applicable. Compare the supplied customer score to the documented score threshold. Make clear that satisfying a published score threshold does not guarantee approval: card approval remains subject to an application and underwriting.
4. **Savings conditions.** State the savings account's minimum opening deposit, ongoing minimum balance, and paperless or paper-statement requirement. Include a material withdrawal limit or scenario-relevant charge when documented, but do not count a merely contingent charge as a known cost.
5. **Assumptions and bonus conditions.** State that the estimate assumes the balance remains deposited throughout the stated period and that product eligibility is maintained. If terms require an active, good-standing, or profile-linked card, disclose that condition without claiming it has already happened.
6. **Advice-only status.** State that no account has been opened, no card application submitted, no products linked, and no funds transferred.

Use this response pattern, substituting only facts found in the current task materials:

> For your stated [balance] over [period] and your [fee/subscription] constraint, I recommend **[official savings account]** with **[official card]**. The savings account pays [base APY]% base APY, and the card adds [applicable bonus]%, for **[effective APY]% APY**. If [balance] remains deposited for [period], that is approximately **$[interest]** in interest and **$[net return] net return** after known recurring costs. The card has a **[annual-fee amount] annual fee**. Your stated score of [score] [meets/does not meet] the documented [minimum-score] minimum; final approval remains subject to an application and underwriting. The savings account requires a **$[opening deposit] opening deposit**, a **$[ongoing minimum] ongoing minimum balance**, and **[statement requirement]**. This assumes the balance remains deposited and all card/account eligibility conditions remain satisfied; contingent transaction charges are not included. This is advice only: no account has been opened, no card application submitted, no products linked, and no funds transferred.

A short explanation of why a higher-bonus card was excluded for an annual fee or subscription requirement is allowed after the answer, but it must not obscure the selected pairing.

## Non-action boundary

For a recommendation or comparison request:

- Do not call account-opening, credit-card-application, product-linking, or fund-transfer tools.
- Do not request funding instructions or imply that an account, application, link, or transfer is pending or complete.
- Do not transfer to a human agent merely because an evidence-backed recommendation requires calculation.

Enter an execution workflow only after the customer explicitly selects the exact product or products and explicitly authorizes the requested action. Before **any banking action**, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For an authorized savings opening, additionally verify the active-checking requirement, checking tenure, savings-account-count limit, account standing, exact official account class, required opening deposit, statement requirement, and funding choice. Obtain separate explicit authorization before a transfer.

## Pre-send checklist

- [ ] Answered the latest question directly with one evidence-supported pairing.
- [ ] Named the official savings account and card.
- [ ] Included base APY, applicable card bonus, effective APY, and dollar estimate.
- [ ] Explicitly stated the selected card's annual fee.
- [ ] Applied stated fee and subscription constraints and did not stack card bonuses.
- [ ] Disclosed opening deposit, ongoing minimum balance, and statement requirement.
- [ ] Compared stated score against the documented threshold and qualified approval.
- [ ] Stated stable-balance and ongoing-bonus-eligibility assumptions.
- [ ] Confirmed that no products were opened, applied for, linked, or funded.

## Calculator interface

Run `scripts/rank_combinations.py` with one JSON object on stdin. Every value must be extracted from the current task's supplied evidence.

```json
{
  "deposit": 0,
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
      "notes": ["Documented and customer-applicable fact"]
    }
  ]
}
```

The script emits `eligible_ranked`, `rejected`, `highest_net_return`, and explicit assumptions. It applies only the highest supplied card bonus and highest supplied checking boost. The executor must decide which supplied bonuses are documented and applicable, then use the output to construct the complete customer-facing answer above.
