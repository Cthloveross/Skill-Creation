---
name: everyday-credit-card-cashback-advice
description: Explain and compare the available Rho-Bank personal credit cards for an everyday-purchase customer, including cash-back rates, annual fees, eligibility gates, and spend-based net-reward comparisons. Use for informational card-selection conversations; do not use it to submit applications or alter an account.
---

# Everyday Credit Card Cash-Back Advice

Use this Skill when a customer wants factual, non-transactional help selecting a card for everyday purchases. Product information is in `references/card_catalog.md`.

## Scope and safeguards

This workflow provides product education only. It does not apply for a card, access an account, determine approval, promise an offer, or waive a fee. Public product information does not require identity verification or account lookup.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

If the customer changes the request into an application, account-specific inquiry, or another banking action, stop this informational workflow and follow the applicable action procedure and all mandatory controls. Never infer a customer's credit score, subscription, invitation status, approval, or promotional eligibility.

## Conversation method

1. **Answer the question already asked.** For a request about rates and fees, present the available card options plainly before requesting more information. State the annual fee and cash-back rate, and qualify rewards as applying to eligible purchases when that is how the product terms are stated.
2. **State eligibility separately from value.** Explain that Gold requires at least a 720 credit score and an active Rho-Bank+ subscription; Platinum states a 750 minimum score; Diamond Elite is invitation-only and indicates at least 780 for consideration. Meeting a stated score does not itself guarantee approval or an invitation.
3. **Use net annual rewards for a spend comparison.** Let `S` be annual eligible purchase spend and show the applicable formula: `cash back = S × rate`; `net value before other costs = cash back − annual fee`. Returns or credits can reduce rewards, and fees, interest, cash advances, balance transfers, and cash-equivalent transactions are not eligible where the product terms exclude them.
4. **Give the useful Gold-versus-Platinum threshold when both products are available.** With the published standard terms, Platinum's 10% less its $200 annual fee exceeds Gold's 2.5% with no annual fee when annual eligible spend is more than approximately $2,666.67. At exactly that amount the modeled net values tie. This is a rewards-and-fee comparison only, not an approval prediction.
5. **Treat Diamond Elite conditionally.** Its standard $495 annual fee, invitation-only access, and potentially applicable invitation promotion mean it should not be represented as generally available or fee-free. At the standard fee, its 5% rewards less $495 beats Gold's 2.5% no-fee rewards only above approximately $19,800 of eligible annual spend. If Platinum is accessible on its published standard terms, Platinum has both the higher listed rate and lower annual fee than Diamond Elite; still avoid equating distinct eligibility or purchase rules.
6. **Ask only for decision-relevant missing information.** After answering factual questions, invite the customer to share approximate yearly eligible everyday spend, approximate credit-score range, and whether they have Rho-Bank+. If they do not know their score, do not pressure them; offer the conditional comparison instead.
7. **Handle promotions by date.** Do not describe the Platinum first-year-fee promotion as available unless the application date is within its stated 2024-06-01 through 2024-12-31 window. Use an explicitly supplied or observed current date if promotion timing matters. Do not invent an alternative waiver or rebate threshold absent from the catalog.

## Recommended response structure

For the ordinary fact request in this workflow:

- Start with a compact bullet list of Gold, Platinum, and Diamond Elite cash-back rates and standard annual fees.
- Follow with a short eligibility note, especially when the customer has not supplied a score or subscription status.
- Explain the Gold/Platinum break-even amount in plain language.
- Mention that the listed Platinum fee-waiver promotion ended on 2024-12-31 when the current date is after that date.
- Close by asking for optional annual spend, approximate score range, and Rho-Bank+ status to make the recommendation conditional and more specific.

Avoid presenting APR, credit limits, virtual cards, or redemption thresholds unless the customer asks or they materially affect the decision. If mentioned, label them by product and do not blend terms across cards.

## Optional calculation helper

Use `scripts/compare_rewards.py` when a customer supplies an annual eligible-spend estimate or when comparing a different set of published card terms. The script reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "annual_spend": "non-negative decimal amount",
  "cards": [
    {"name": "card label", "cashback_rate_percent": "non-negative decimal", "annual_fee": "non-negative decimal"}
  ]
}
```

`annual_spend` may be a JSON number or decimal string. The output contains each card's gross rewards and net annual value rounded to cents, sorted from highest to lowest net value, plus pairwise break-even spending points. A `null` break-even means that the two rates are equal, so a spend threshold cannot reverse their fee difference.

Run it from the package root with a JSON object containing the actual customer estimate and the relevant catalog terms:

```sh
python3 scripts/compare_rewards.py <<'JSON'
{ "annual_spend": "<customer annual eligible spend>", "cards": [ ...published card terms... ] }
JSON
```

Check that every returned card has `gross_rewards`, `annual_fee`, and `net_value`, and that the card order agrees with the returned values. Use the result as an aid; communicate assumptions, eligibility gates, and non-reward costs in the customer-facing answer.

## Missing or unsupported information

Do not guess a credit score, actual spend, approved limit, current promotion, rebate spending threshold, or final eligibility. Explain what is known and give conditional guidance. If the customer requests details not present in the catalog, say that the available product information does not establish them rather than fabricating an answer.
