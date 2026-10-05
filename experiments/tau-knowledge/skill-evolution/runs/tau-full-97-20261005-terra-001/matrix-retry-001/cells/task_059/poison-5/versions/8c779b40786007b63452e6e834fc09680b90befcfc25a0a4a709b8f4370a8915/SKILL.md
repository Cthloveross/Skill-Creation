---
name: evidence-backed-savings-card-recommender
description: Give a direct, evidence-backed advisory recommendation for a savings-account and credit-card pairing from supplied product terms and customer facts. Use for APY, card-bonus, annual-fee, subscription-cost, balance-requirement, and credit-threshold comparisons; do not use it to open products, apply for cards, link products, or move funds without explicit authorization.
---

# Evidence-Backed Savings and Card Recommender

Use the current task's supplied product documentation, clarification record, and read-only observations as the source of truth. This is an **advisory workflow** unless the customer separately and explicitly authorizes an identified banking action.

## Mandatory advisory behavior

When the customer asks which savings/card combination is best, asks a final comparison question, or asks for a no-fee alternative:

1. Answer the question directly in the same response using the supplied terms.
2. Give one best supported recommendation when the customer asks for a single best option.
3. Do not say terms are unavailable if relevant supplied documents state the terms.
4. Do not ask again for facts already supplied in clarifications or observations.
5. Do not substitute a plan to compare, a generic offer of help, or a human transfer for the completed recommendation.

A request for advice, comparison, eligibility discussion, or an estimate is **not** authorization to open an account, submit a card application, link products, transfer money, or perform another banking action.

## Non-action boundary

For an advisory request:

- Do not call banking-action tools or application tools.
- Do not open products, link products, submit a card application, or move money.
- Do not present an action as completed unless a supported tool has actually confirmed it.
- State plainly that no account was opened, no card application was submitted, no products were linked, and no funds were transferred.

Before any later banking action, verify customer identity, authority, ownership, product eligibility, available funds or credit, fees, limits, cutoffs, exact product and destination details, and required confirmations. Obtain an explicit selection of the exact product and explicit authorization for the exact action.

## Evidence and decision procedure

1. **Collect binding customer constraints.** Read the latest request and every clarification. Treat an explicit deposit amount, horizon, no-annual-fee preference, refusal of a paid subscription, stated credit score, and request for one answer as binding.
2. **Extract terms from the supplied documents.** For each supportable savings/card pairing, record:
   - official savings-account and card names;
   - savings base APY;
   - card bonus documented specifically for that savings account;
   - card annual fee and any required subscription cost;
   - card score threshold and any documented requirements;
   - savings opening deposit, ongoing balance, statement-delivery, and material transaction conditions; and
   - conditions for keeping the bonus, such as good standing or profile linkage.
3. **Apply constraints before ranking.** Exclude a card with an annual fee when the customer requires no annual fee. Exclude a pairing that requires a paid subscription when the customer rejects one. Do not treat a temporary fee waiver as a no-fee product unless the documented terms and requested period establish that it satisfies the constraint.
4. **Apply bonus rules accurately.** Only apply a bonus to the savings account for which it is documented. Where card bonuses do not stack, use only the highest qualifying card bonus. Add checking, relationship, or direct-deposit boosts only when both their amount and the customer's qualification are documented. Never infer an unquantified boost.
5. **Calculate the comparable estimate.** For a stable one-year balance:

   `effective APY = base APY + documented applicable additive bonuses`

   `estimated one-year interest = deposit × effective APY / 100`

   `estimated net return = interest − known annual card fees − known required annual subscription costs − other known annual recurring costs`

   APY is annualized already; do not compound an APY a second time. Do not subtract transaction-dependent charges unless the scenario establishes that they apply.
6. **Select and answer.** Recommend the compliant pairing with the highest supported net return. If material information prevents a ranking, identify the precise missing term and give the strongest conditional answer supported by the documents. Never invent rates, fees, approval status, account status, or eligibility.

Use `scripts/rank_combinations.py` for repeated arithmetic and ranking. It is an arithmetic aid only: the executor must supply document-grounded inputs and remains responsible for eligibility, disclosures, and authorization boundaries.

## Completed response requirements

A completed advisory response must include all applicable elements below. Do not leave placeholders in the customer-facing response.

1. **Direct recommendation first.** Identify the official savings account and card, and explicitly tie the choice to the customer's balance, period, and fee/subscription constraint.
2. **Transparent return math.** State the base APY, the applicable card bonus, the addition yielding the effective APY, and the dollar interest estimate for the customer's stated balance and horizon. State the resulting net return after known recurring costs.
3. **Fees and card eligibility.** Explicitly say the selected card's annual fee, including “$0 annual fee” where applicable. Compare a documented score minimum to the customer's supplied score. A qualifying stated score is not approval: say that final approval remains subject to the application and underwriting.
4. **Savings disclosures.** State the recommended savings account's documented minimum opening deposit, ongoing minimum balance, and paperless or paper-statement requirement. Mention a material documented transaction limit or contingent charge when relevant, but distinguish it from the stable-balance estimate.
5. **Assumptions and bonus conditions.** State that the estimate assumes the funds remain deposited for the stated period and that eligibility is maintained. If the bonus requires the card to remain active, in good standing, and/or linked under the required profile, disclose that condition without claiming it has already occurred.
6. **No-action status.** State that the response is a recommendation only and that no account was opened, card application submitted, products linked, or funds transferred. Invite the customer to explicitly select the products if they want to discuss authorized next steps.

Use concise language, but do not omit a material figure or condition merely to be brief. A reliable structure is:

> For your stated balance over the requested period and your fee constraint, I recommend **[Savings Account]** with **[Card]**. The documented [base]% base APY plus the [bonus]% card bonus equals **[effective]% effective APY**. That is approximately **$[interest]** in interest and **$[net] net return** for the period after known recurring costs. The card has a **[annual fee] annual fee**. Based on the score you provided, you appear to meet the documented minimum of [minimum], but approval is subject to application and underwriting. The savings account requires a **[opening deposit] opening deposit**, an **[ongoing balance] ongoing minimum balance**, and **[statement requirement]**. This assumes the balance remains deposited and the card/account eligibility conditions remain satisfied; it excludes contingent transaction charges. I have not opened an account, applied for a card, linked products, or transferred funds.

If an otherwise attractive option is excluded for violating the customer's no-fee or no-subscription constraint, one short explanation is appropriate. Do not dilute a supported single recommendation with an unnecessary menu of alternatives.

## Pre-send checklist

Before sending the advisory answer, verify that it contains:

- the official recommended savings-account and card names;
- the selected card's explicit annual-fee statement;
- base APY, applicable card bonus, effective APY, and dollar estimate;
- the requested balance and time-horizon assumption;
- known required subscription or recurring cost treatment;
- opening deposit, ongoing minimum balance, and statement requirement;
- documented credit-threshold comparison and underwriting qualification;
- maintained-eligibility conditions for the bonus; and
- the explicit no-action status.

## If the customer later authorizes execution

Only enter an execution workflow after the customer expressly selects the exact product(s) and authorizes the specific action.

1. Verify identity and authority using the supported process.
2. Recheck all savings-opening prerequisites: active checking, tenure, personal-savings-account limit, collections and negative-balance restrictions, and product-specific requirements.
3. Confirm exact official product names, applicable fees, statement requirement, opening-deposit amount, funding choice, and final authorization.
4. Open a product only after every prerequisite and authorization is confirmed.
5. Obtain separate explicit authorization before any funding transfer, and verify source ownership, available balance, amount, applicable limits, cutoff, and destination.
6. Report only tool-confirmed outcomes. If funding is deferred, communicate only a documented funding deadline and consequence.

## Calculator interface

Run `scripts/rank_combinations.py` with one JSON object on stdin. It emits one JSON object on stdout. All values must come from the current task evidence.

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
      "id": "documented-runtime-label",
      "savings_account": "Official savings account name",
      "card": "Official card name",
      "base_apy_percent": 0,
      "card_apy_bonuses_percent": [0],
      "checking_apy_boosts_percent": [],
      "other_additive_apy_bonuses_percent": [],
      "annual_card_fee": 0,
      "annual_subscription_fee": 0,
      "other_known_annual_costs": 0,
      "notes": ["Documented, customer-applicable fact"]
    }
  ]
}
```

The output contains `eligible_ranked`, `rejected`, `highest_net_return`, and calculation assumptions. It uses only the highest supplied card bonus and highest supplied checking boost; it does not establish that a supplied bonus is actually applicable.
