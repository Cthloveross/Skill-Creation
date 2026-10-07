---
name: savings-card-net-yield-advisor
description: Provide evidence-based comparisons of savings accounts and credit cards when a customer wants to maximize projected savings interest less annual card fees. Use for conditional credit eligibility, account balance and withdrawal-limit fit, APY bonus stacking, and safe next steps before any account opening or application.
---

# Savings and Card Net-Yield Advisor

Use this Skill for a **read-only recommendation** based on the product documents, customer clarifications, and read-only observations supplied for the current task. Do not open an account, submit a card application, transfer money, or modify customer data while performing the comparison.

## Non-negotiable recommendation rule

When supplied evidence documents a viable comparison, provide the comparison directly. Do **not** claim that terms are unavailable, defer to a human agent, or ask for information that the customer has already said is unknown when a conditional recommendation can answer the request.

An unknown credit score does not prevent a useful answer. If the customer requests a conditional recommendation, state the best documented combination conditionally and name the exact score, subscription, underwriting, or other requirement that remains unconfirmed. Never imply that a customer is approved or certain to qualify merely because a published threshold exists.

## Extract current-task facts

Use only facts supported by the current materials. Extract:

- The customer's objective, comparison period, planned deposit or maintained balance, and whether withdrawals are replenished.
- Expected monthly withdrawal count.
- For each plausible savings account: official name, APY or applicable tier, opening and ongoing minimums, maintenance-fee condition, withdrawal limit, and documented bonuses.
- For each plausible card: official name, annual fee, minimum score, subscription prerequisite, other material eligibility requirements, and the bonus for the specific savings account.
- Any stacking policy and any qualifying linked-checking boost actually supported by the evidence.
- Which requirements are confirmed, unknown, or known to fail.

A stated intended deposit is a modeling assumption, not proof that money is available for a transfer. A profile lookup is not automatically completed identity verification. Those distinctions do not prevent a read-only product recommendation.

## Evaluate candidates

1. **Screen account-use fit.** Compare the modeled balance with both documented opening and ongoing minimums. Compare expected monthly withdrawals with the account's documented monthly limit. Treat `-1` as unlimited only where the source expressly says that it means unlimited.
2. **Build the APY.** Add the base APY and only bonuses that are expressly documented for that account and product pairing. When a document requires both products under the same customer profile, disclose that condition.
3. **Apply stacking rules.** Do not add more than one credit-card APY bonus when the evidence says only the highest card bonus applies. Do not assume a checking boost unless the customer's documented checking account is a qualifying pairing. Add different types of bonuses only if the evidence explicitly permits it.
4. **Classify eligibility.** Use `eligible` only if all material requirements are known met. Use `conditional` if an unknown requirement could be met. Use `ineligible` if a known requirement fails. Treat approval and underwriting as conditional even where the customer reports meeting a score threshold.
5. **Calculate.** Use `scripts/compare_net_yield.py` with facts extracted from the current task. Evaluate one card per result; include a no-card alternative when it is a supported useful fallback.
6. **Choose the answer.** Normally lead with the highest-net eligible result. If the customer explicitly asks for a conditional recommendation and a higher-net conditional path exists, lead with that conditional path and then identify the best supported fallback if useful.

## Required visible response structure

The customer-facing response must make the decision auditable. Include all applicable items below in the visible prose, rather than leaving them only in tool output or internal reasoning.

1. **Recommendation first:** State the official savings-account and card names.
2. **Conditionality first:** If any material card requirement is unknown, begin the recommendation with language such as: “If you meet the documented [requirement] and are approved, ...” State the exact threshold or prerequisite. State separately which prerequisites are already confirmed.
3. **APY arithmetic:** Show base APY `+` card bonus `=` effective APY. Do not merely state the final rate.
4. **One-year money calculation:** State the modeled balance, projected gross interest, documented annual card fee, and interest-minus-annual-fee result. Explicitly say that the result excludes transaction, withdrawal, maintenance, or other costs whose applicability or amount is not established.
5. **Operating fit:** State the account's ongoing minimum and directly compare it to the expected balance. State the withdrawal limit and directly say whether the customer's expected withdrawals are within it. If replenishment supports the estimate, say that the projection assumes the balance remains near the modeled amount.
6. **Practical next step:** Ask the customer to select the products before taking action. Identify remaining checks or application steps without promising approval.

For example, the required reasoning pattern is: base APY plus the documented pairing bonus equals the effective APY; modeled balance multiplied by the one-year APY gives the approximate annual interest; subtract the documented annual fee. Use current-task values, not preset values.

Do not substitute unrelated card cash-back rates, sign-up bonuses, promotional APRs, or fee waivers for the requested interest-less-annual-fee comparison unless their amount and applicability are both established and the customer asks to include them.

## Calculation conventions

- Treat stated APY as an effective annual yield.
- For `d` modeled days, calculate gross interest as `balance × ((1 + APY / 100)^(d / 365) - 1)`.
- For a one-year stable-balance model, this is approximately `balance × APY`.
- Subtract only supplied, applicable annual fees. Do not assume that a conditional fee waiver applies.
- If the balance is not expected to stay near the modeled value and no dated balance schedule is available, explain that a precise stable-balance estimate is not supportable.
- The account may compound daily while interest posts monthly; neither fact justifies altering a stated APY.

## Script interface

Run `scripts/compare_net_yield.py` with one JSON object on standard input. It emits one JSON object on standard output, performs no retrieval, and performs no banking action.

Input schema:

```json
{
  "balance": 0,
  "months": 12,
  "withdrawals_per_month": 0,
  "balance_is_replenished": true,
  "options": [
    {
      "savings_name": "official savings account name",
      "base_apy_pct": 0,
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "withdrawal_limit": null,
      "checking_boost_pct": 0,
      "relationship_bonus_pct": 0,
      "savings_annual_fee": 0,
      "savings_eligibility": "eligible",
      "cards": [
        {
          "card_name": "official card name or no-card option",
          "bonus_apy_pct": 0,
          "annual_fee": 0,
          "eligibility": "eligible"
        }
      ]
    }
  ]
}
```

`withdrawal_limit` is an integer, `null` when not documented, or `-1` only when supplied evidence explicitly defines it as unlimited. Eligibility values are `eligible`, `conditional`, `unknown`, or `ineligible`. The output provides ranked results, both the best eligible and best conditional results, component rates, fit facts, and warnings. Address every warning relevant to the recommended result in the response.

Runnable invocation pattern:

```sh
python3 scripts/compare_net_yield.py <<'JSON'
{"balance": BALANCE, "months": 12, "withdrawals_per_month": WITHDRAWALS, "balance_is_replenished": true, "options": OPTIONS}
JSON
```

## Before any banking action

Analysis is not an authorization to act. Before describing or performing any banking action, preserve and satisfy this control verbatim:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a personal savings opening, verify identity; an active checking account; fewer than five personal savings accounts; no collections or negative balances; and the required checking-account tenure. Obtain the customer's explicit selection of the exact official account class before opening it. Verify funding details and receive separate authorization before any transfer. Do not submit a credit-card application unless the customer explicitly asks to proceed and the authorized workflow supports it.
