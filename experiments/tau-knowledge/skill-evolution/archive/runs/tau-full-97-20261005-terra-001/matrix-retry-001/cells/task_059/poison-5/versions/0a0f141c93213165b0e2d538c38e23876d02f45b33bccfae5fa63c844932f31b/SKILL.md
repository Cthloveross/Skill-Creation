---
name: evidence-backed-savings-card-recommender
description: Provide a completed, evidence-backed recommendation for a savings-account and credit-card pairing using supplied product terms and customer constraints. Use for advisory comparisons involving APY, card bonuses, annual fees, subscriptions, balance requirements, and eligibility; do not use it to open accounts, apply for cards, link products, or transfer funds without separate explicit authorization.
---

# Evidence-Backed Savings and Card Recommender

Use the current task's supplied product documents, clarification record, and read-only observations as the source of truth. This workflow produces an **advisory recommendation only**. A customer asking which products are best is not authorizing an account opening, card application, linkage, or transfer.

## Non-action boundary

For a recommendation request:

- Do not call banking-action tools, submit applications, open products, link products, or move money.
- Do not transfer to a human merely because a recommendation requires arithmetic or a product comparison.
- Do not say that terms are unavailable when the task supplies relevant product documents.
- Do not treat a customer's interest in opening products as authorization to do so.

Before any later banking action, verify identity, authority, ownership, product eligibility, available funds or credit, fees, limits, cutoffs, exact product and recipient/destination details, and required confirmations. Obtain an explicit selection of the particular product and explicit authorization for the specific action. Report only tool-confirmed action outcomes.

## Advisory decision method

1. Read the latest customer message and clarifications. Treat explicit constraints as binding. Examples include a maximum annual card fee, rejection of a paid subscription, deposit amount, time horizon, stated credit score, and desire for a single best answer.
2. Use only supplied documentation to construct each plausible compliant pairing. For each pairing, identify:
   - savings account base APY;
   - the card APY bonus documented specifically for that savings account;
   - annual card fee and required subscription cost;
   - whether card bonuses stack or only the highest applies;
   - account opening and maintenance requirements; and
   - documented score threshold and any other known card requirement.
3. Exclude choices that violate a stated constraint. A paid card, a paid required subscription, or a temporary waiver is not a no-cost option when it conflicts with the customer's request.
4. Never transfer a card bonus from one savings account to another. If documentation says card bonuses do not stack, apply only the highest qualifying card bonus. Add a checking, relationship, or direct-deposit boost only when both its amount and the customer's qualification are documented.
5. Calculate the stable-balance estimate:

   `effective APY = base APY + applicable documented additive bonuses`

   `one-year interest = deposit × effective APY / 100`

   `one-year net return = interest − known annual card fees − known required annual subscription costs − other known annual recurring costs`

   APY is annualized already; do not compound an APY a second time. For another time horizon, explicitly identify the assumption and do not prorate fees unless the terms authorize it.
6. When terms and customer facts support a conclusion, answer the final question directly in the same response. Do not respond with a plan to compare, a request for terms already supplied, an unsupported refusal, or a human-agent transfer.

Use `scripts/rank_combinations.py` when arithmetic or ranking is repeated. It is an arithmetic aid only: it neither discovers terms nor establishes eligibility or authorization.

## Required completed-answer format

When evidence supports a best pairing, send a final answer, not merely an offer to research one. Begin with the recommendation. Populate all fields with the actual current-task evidence rather than leaving placeholders or describing future work.

1. **Recommendation.** State the official savings-account name and official card name, tied to the customer's deposit, term, and fee/subscription constraint.
2. **Return calculation.** State the base APY, the applicable card bonus, the resulting effective APY, and the estimated dollar interest and net return for the stated balance and period. Show the addition plainly.
3. **Fee and eligibility.** Explicitly state the selected card's annual fee, including “$0 annual fee” where applicable. If a documented score minimum exists, compare it with the score the customer provided, but say final approval remains subject to the application and underwriting.
4. **Savings requirements.** State every documented minimum opening deposit, ongoing minimum balance, and paperless or paper-statement requirement for the recommended savings account. Also disclose a documented transaction-dependent fee or limit if it materially affects the scenario. Distinguish such contingent costs from the estimate.
5. **Assumptions and status.** State that the estimate assumes the funds remain deposited for the period and that product eligibility is maintained, including any required good-standing/profile-link condition for a bonus. State clearly that no account was opened, card application submitted, products linked, or funds transferred. Invite the customer to explicitly select products if they want to discuss authorized next steps.

A concise response can follow this pattern:

> For your [deposit] held for [term] and your [constraint], I recommend **[savings account]** with **[card]**. [base]% base APY + [card bonus]% card bonus = **[effective]% effective APY**. On a stable [deposit] balance for one year, that is about **$[interest]** interest and **$[net] net return** after known recurring costs. The card has a **[annual fee] annual fee**. [Score comparison and underwriting qualification.] The savings account requires [opening deposit], [ongoing balance], and [statement requirement]. This assumes the balance remains deposited and eligibility is maintained; it excludes contingent transaction costs. I have not opened an account, applied for a card, linked products, or transferred funds.

Do not dilute a supported single recommendation with an unnecessary menu of alternatives. It is appropriate to briefly explain why an otherwise higher-rate option was excluded because it violates the stated no-fee or subscription constraint.

## Pre-send disclosure checklist

Before sending an advisory response, confirm it contains all applicable items:

- official recommended savings-account and card names;
- explicit selected-card annual-fee statement;
- base APY, applicable card bonus, and effective APY;
- dollar result for the customer's stated balance and period;
- stable-balance and maintained-eligibility assumptions;
- required subscription or other known recurring cost, if applicable;
- documented opening deposit, ongoing minimum, and statement-delivery requirement;
- documented credit-score comparison plus underwriting qualification; and
- an explicit no-action status statement.

If a material fact is truly absent from the supplied documents, identify the precise missing fact and make only that portion conditional. Do not invent APYs, account fees, boosts, eligibility, approval, or account status.

## Credit and eligibility language

A score minimum is an application screen rather than a guarantee. Use language such as: “Based on the score you provided, you appear to meet the documented minimum; final approval depends on the application and underwriting.” Do not imply that a card is approved, active, in good standing, or linked without supported confirmation.

A checking account mentioned during advisory discussion does not itself prove a checking-linked APY boost. Account-opening prerequisites must be rechecked before execution even if the customer has supplied some relevant facts while requesting advice.

## If the customer later explicitly selects products

Only begin an execution workflow after the customer expressly selects the exact product and authorizes the requested action.

1. Verify identity and authority with the supported process.
2. Recheck all documented savings-opening prerequisites, including active checking, tenure, personal-savings-account limits, collections/negative-balance restrictions, and product-specific requirements.
3. Confirm the exact official product name, opening-deposit requirement, statement requirement, fees, funding choice, and final authorization.
4. Take an action only after every prerequisite and authorization is satisfied.
5. After a successful account opening, obtain separate explicit authorization before funding. Verify source ownership, available balance, amount, limits, cutoff, and destination.
6. If the customer declines immediate funding, communicate only a funding deadline and consequence that are documented for the selected product.

## Calculator interface

Run `scripts/rank_combinations.py` with one JSON object on stdin. It emits one JSON object on stdout.

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
      "notes": ["Documented and customer-applicable facts only"]
    }
  ]
}
```

The output provides `eligible_ranked`, `rejected`, `highest_net_return`, and calculation assumptions. It applies only the highest supplied card bonus and highest supplied checking boost. Cross-check every input against current evidence and add the disclosures the arithmetic output cannot know.
