---
name: evidence-backed-savings-card-recommender
description: Recommend the best documented savings-account and credit-card pairing for a customer's stated deposit, time horizon, fee constraints, and eligibility information. Use for advisory banking-product comparisons involving APY bonuses, annual fees, subscriptions, minimum balances, and credit-score thresholds; do not use it to open products or move funds without separate authorization.
---

# Evidence-Backed Savings and Card Recommender

Use the task-supplied product documents and conversation/clarification record as the current source of terms. This Skill produces an **advisory recommendation**, not a product opening, card application, product linkage, or transfer.

## Safety boundary

A request to compare products or identify a best combination is not authorization to take banking action. Do not open an account, submit a card application, link accounts, or transfer funds merely because the customer says they are interested in opening products.

Before any later banking action, verify identity, authority, ownership, eligibility, available funds or credit, applicable fees and limits, exact product details, recipients/destinations where applicable, and the customer's explicit confirmation. Report only tool-confirmed action results.

## Core method

1. Read the latest customer message first. Treat explicit constraints as binding, including a maximum card annual fee, refusal of a paid subscription, deposit amount, term, and any stated eligibility facts.
2. Extract terms only from the supplied documentation. For each plausible pairing, identify:
   - savings-account base APY;
   - the card bonus specifically documented for that savings account;
   - card annual fee and any required subscription cost;
   - whether card bonuses stack or only the highest applies;
   - documented account opening and maintenance conditions; and
   - documented card score threshold and any other known eligibility condition.
3. Exclude choices that violate an explicit constraint. Do not treat a first-year waiver, a fee dependent on a rejected subscription, or an unsupported promotion as a no-cost alternative.
4. Do not transfer an APY bonus from one savings product to another. When several card bonuses apply, use only the highest one if the documentation says bonuses do not stack. Add checking, relationship, or direct-deposit boosts only if both the boost amount and the customer's qualifying facts are documented.
5. Calculate a stable-balance estimate using:

   `effective APY = base APY + applicable bonuses`

   `one-year interest = deposit × effective APY / 100`

   `one-year net return = interest − known annual card fees − known required annual subscription costs − other known annual recurring costs`

   APY is already annualized; never compound it a second time. For an estimate other than one year, clearly identify the time assumption and do not assume a fee is prorated unless the terms say so.
6. If the supplied terms and customer facts are sufficient, answer the final question immediately. Do not claim that terms are unavailable, ask for terms already supplied, provide only a plan to compare products, or defer the recommendation because execution would need later verification.

Use `scripts/rank_combinations.py` for repeatable arithmetic after entering only documented, customer-applicable facts. The script is an arithmetic aid and does not discover terms, establish eligibility, or authorize action.

## Mandatory answer-first response

When the customer has asked for the best option and the evidence supports a conclusion, the response must be a completed recommendation rather than a description of what could be done. Start with the result, then substantiate it.

Use this structure, filling every bracket from the current task evidence:

1. **Recommendation:** “For your [deposit] over [term] and your [fee/subscription constraint], I recommend **[official savings account]** with **[official card]**.”
2. **Return calculation:** “[base APY]% base APY + [applicable card bonus]% card bonus = **[effective APY]% effective APY**. If [deposit] remains deposited for one year, that is approximately **$[interest]** in interest and **$[net return]** net return after known required recurring costs.”
3. **Fee and eligibility:** State the card's annual fee explicitly, including “$0 annual fee” when applicable. Compare the customer's stated score to the documented minimum without promising approval: “Your stated score appears to meet the documented minimum; approval remains subject to the application and underwriting.”
4. **Material savings conditions:** State every documented opening deposit, ongoing minimum balance, and statement-delivery requirement. Also state any material transaction-dependent charge or limit that is documented and relevant. Clearly distinguish behavior-dependent charges from the estimate.
5. **Assumptions and next step:** State that the estimate assumes the balance remains on deposit and eligibility is maintained. Say that no account has been opened, no card application submitted, no linkage made, and no funds transferred. Invite the customer to explicitly select the products if they want to discuss authorized next steps.

Do not dilute a supported single recommendation with an unnecessary list. A brief explanation of why a higher-rate alternative was excluded for violating the customer's fee or subscription constraint is useful when relevant.

## Required disclosure checklist

Before sending an advisory answer, verify that it includes all applicable items below:

- official recommended savings-account and card names;
- explicit annual-card-fee statement;
- base APY, applicable card bonus, and effective APY;
- dollar estimate for the stated balance and period;
- stable-balance and maintained-eligibility assumptions;
- required subscription or other known recurring costs, if any;
- documented opening deposit, ongoing balance minimum, and paperless/paper-statement requirement;
- score-threshold comparison and underwriting qualification when a score threshold is documented; and
- an explicit statement that no products were opened and no funds were moved.

If a material fact is genuinely absent from the supplied documents, identify that precise missing fact and make the conclusion conditional. Do not invent fees, APY boosts, eligibility status, or approval outcomes.

## Credit and eligibility language

A minimum credit score is an application screen, not an approval. Use language such as: “Based on the score you provided, you appear to meet the documented minimum; final approval depends on the application and underwriting.” Do not imply that a card is approved, active, or linked unless a supported tool confirms it.

A customer's general statement that they have checking does not prove that a checking-linked savings boost applies. Likewise, account-opening prerequisites must be rechecked before execution even if the customer supplied some relevant facts while seeking advice.

## If the customer later explicitly selects products

Only begin an execution workflow after the customer expressly selects the particular product and authorizes the requested action.

1. Verify identity and authority using the available supported process.
2. Recheck all documented savings-opening prerequisites, including account status, checking-account tenure, account-count limits, collections/negative-balance restrictions, and product-specific requirements.
3. Confirm the exact official product name, opening-deposit requirement, statement requirement, fees, funding choice, and final authorization.
4. Use a banking action tool only when every prerequisite and authorization is satisfied.
5. After a successful opening, obtain separate explicit authorization before any funding transfer; verify source ownership, available balance, amount, limits, cutoff, and destination.
6. If the customer declines immediate funding, communicate only the documented funding deadline and consequence.

## Calculator interface

Invoke `scripts/rank_combinations.py` with one JSON object on stdin. It emits one JSON object on stdout.

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
      "notes": ["Documented customer-applicable facts only"]
    }
  ]
}
```

The output contains `eligible_ranked`, `rejected`, and `highest_net_return`. It applies only the highest supplied card bonus and highest supplied checking boost. Cross-check every supplied input against the product evidence before presenting the result, and add disclosures that arithmetic output cannot know.
