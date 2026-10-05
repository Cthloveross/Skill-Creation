---
name: evidence-backed-savings-card-recommender
description: Provide a completed, evidence-backed recommendation for a savings account and credit card pairing using supplied product terms and customer facts. Use when a customer asks to maximize yield or net return subject to fees, subscriptions, balance requirements, or credit eligibility. This is advisory only unless the customer explicitly authorizes a specific banking action.
---

# Evidence-Backed Savings and Card Recommender

Use the supplied product documents, clarification history, and read-only observations as the current source of truth. This Skill is for completing the recommendation, not merely describing how one could make it.

## First rule: answer the final question now

When the customer asks for the best pairing, a no-annual-fee alternative, or confirmation of the best net return:

- Give the customer-facing recommendation in the same response.
- Use supplied terms directly; do not claim that terms are unavailable when they appear in the supplied evidence.
- Do not respond only with a plan to compare options, a request for already-provided facts, a generic capability statement, or a transfer to a human agent.
- If the customer requests one best choice, give one best documented choice rather than an unnecessary menu.

An advice or comparison request is **not** authorization to open an account, apply for a card, link products, or transfer funds.

## Method

1. Read the latest customer request and all clarifications. Treat explicit balance, time horizon, fee constraints, subscription refusal, stated credit score, and preference for a single answer as binding.
2. From supplied documents, identify supportable savings/card pairings and extract:
   - savings base APY;
   - card bonus specifically documented for that savings account;
   - card annual fee and required subscription cost;
   - documented credit score minimum and eligibility conditions;
   - required opening deposit, ongoing minimum balance, and statement-delivery requirements; and
   - conditions for retaining the bonus, including active/good-standing and profile-link requirements.
3. Exclude options that conflict with binding constraints. In particular, exclude annual-fee cards when the customer requires no annual fee, and exclude pairings requiring a paid subscription when the customer rejects one.
4. Apply only documented, customer-applicable boosts. Card bonuses apply only to the named savings account. If card bonuses do not stack, apply only the highest qualifying bonus. Do not add an unquantified checking, relationship, direct-deposit, tier, or promotional boost.
5. For a stable balance estimate, calculate:

   `effective APY = base APY + applicable additive bonuses`

   `one-year interest = balance × effective APY / 100`

   `net return = interest − known annual card fees − known required annual subscription costs − other known recurring costs`

   APY already reflects annual compounding. Do not compound APY a second time. Do not subtract contingent transaction charges unless the stated scenario establishes they apply.
6. Recommend the eligible pairing with the highest supported net return. If a required term is genuinely absent, state the exact missing term and provide the strongest conditional answer supported by the evidence.

Use `scripts/rank_combinations.py` when repeated arithmetic or ranking is helpful. It only calculates from evidence-grounded inputs; it does not establish eligibility or authorize action.

## Required customer-facing response

Before sending, write a complete answer with every applicable item below:

1. **Recommendation:** Name the official savings account and official card first, and tie the choice to the stated balance, period, and constraints.
2. **Math:** State the savings base APY, card bonus, effective APY, and estimated interest for the stated balance and period. State net return after known recurring costs.
3. **Annual fee and eligibility:** Explicitly state the selected card's annual fee, including “$0 annual fee” if applicable. Compare the documented score minimum with the customer's stated score. A score comparison is not approval; state that final approval is subject to application and underwriting.
4. **Savings conditions:** State the minimum opening deposit, ongoing minimum balance, and paperless/paper statement requirement. Mention a material withdrawal limit or contingent charge if relevant, but do not treat it as a cost in the estimate unless it is triggered by the scenario.
5. **Assumptions and bonus conditions:** State that the estimate assumes the balance remains deposited for the period and that eligibility is maintained. If documentation requires the card to remain active, in good standing, or linked under the required profile, say so without claiming it has already happened.
6. **No-action status:** Clearly say this is a recommendation only: no account has been opened, no card application submitted, no products linked, and no funds transferred.

Use this structure, replacing all bracketed values with values from the current supplied evidence:

> For your stated [balance] over [period] and your [fee/subscription] constraint, I recommend **[Savings Account]** with **[Card]**. [Savings Account] pays [base APY]% base APY, and [Card] adds [card bonus]%, for **[effective APY]% APY**. On a balance that remains [balance] for [period], that is approximately **$[interest]** in interest and **$[net return] net return** after known recurring costs. [Card] has a **[annual fee] annual fee**. Your stated score of [customer score] meets the documented [minimum score] minimum, although approval remains subject to an application and underwriting. [Savings Account] requires a **$[opening deposit] opening deposit**, a **$[ongoing balance] ongoing minimum balance**, and **[statement requirement]**. This assumes the balance remains deposited and the card/account eligibility conditions remain satisfied; contingent transaction charges are not included. This is advice only: I have not opened an account, submitted a card application, linked products, or transferred funds.

If an attractive option is excluded because it has an annual fee or requires a declined subscription, a single short comparison may be added after the recommendation. Do not let that comparison replace or obscure the selected answer.

## Non-action boundary

For an advisory request:

- Do not call account-opening, application, product-linking, or fund-transfer tools.
- Do not represent any banking action as completed.
- Do not ask for transfer instructions or initiate funding merely because the customer asked for a recommendation.

Only enter an execution workflow after the customer explicitly selects the exact product or products and explicitly authorizes the requested action. Before any banking action, verify identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, exact product and destination details, and all required confirmations.

For an authorized savings opening, also confirm active checking, required checking tenure, savings-account-count limit, account standing, the exact official account class, opening-deposit requirement, statement requirement, and funding choice. Obtain separate explicit authorization before any transfer.

## Pre-send checklist

Confirm the response includes all of the following:

- official savings-account and card names;
- an explicit annual-fee statement for the selected card;
- base APY, applicable card bonus, effective APY, and dollar estimate;
- balance and time-horizon assumption;
- treatment of required subscription and recurring costs;
- opening deposit, ongoing minimum balance, and statement requirement;
- credit-threshold comparison plus underwriting qualification;
- conditions for retaining the bonus; and
- explicit confirmation that no account opening, application, linking, or transfer occurred.

## Calculator interface

Run `scripts/rank_combinations.py` with a JSON object on stdin. All inputs must be extracted from the current supplied evidence.

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
      "notes": ["Documented customer-applicable fact"]
    }
  ]
}
```

The script emits JSON containing `eligible_ranked`, `rejected`, `highest_net_return`, and its calculation assumptions. It selects only the highest supplied card bonus and highest supplied checking boost. The executor remains responsible for determining whether a supplied bonus is documented and applicable.
