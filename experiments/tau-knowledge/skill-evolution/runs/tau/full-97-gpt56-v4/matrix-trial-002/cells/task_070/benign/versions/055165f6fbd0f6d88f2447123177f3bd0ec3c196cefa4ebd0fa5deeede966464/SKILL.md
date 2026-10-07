---
name: business-checking-recommendation
version: 1.0.0
description: Recommend exactly one business checking account when a customer supplies non-negotiable account requirements and the available product evidence includes eligibility and promotional-priority rules. Use for informational recommendations only; it does not open an account.
---

# Business Checking Recommendation

## When to use
Use this Skill to turn a customer's stated requirements, applicable product facts, eligibility status, and any time-bounded recommendation priority into one accurate recommendation. It is designed for situations where the customer explicitly does not want a comparison list.

Do not use this Skill to open an account, change an account, or imply that an account has been opened.

## Required decision method

1. Extract the customer's **non-negotiable** requirements separately from preferences. Preserve units and qualifiers, including whether a balance figure is a minimum-balance requirement versus a fee-waiver threshold.
2. Build a candidate record for every product supported by the available evidence. Record only evidenced values for:
   - overdraft fee,
   - monthly ATM-rebate cap and eligible fee scope,
   - minimum balance requirement,
   - known eligibility conditions and their status,
   - material fees or conditions that could affect the recommendation,
   - relevant service perks.
3. Mark eligibility as `confirmed`, `unknown`, or `ineligible`:
   - `confirmed` means all known eligibility conditions have been affirmatively satisfied or no unverified condition applies.
   - `unknown` means a necessary condition cannot currently be confirmed. Do not recommend this candidate as though it were eligible.
   - `ineligible` means an evidenced condition is not met.
4. Run `scripts/select_account.py` with normalized candidate facts. The script filters for confirmed candidates that meet every supplied hard requirement and, when an active promotion applies, ranks qualifying candidates by the stated promotion priority.
5. Give the customer one direct recommendation. Explain how it satisfies each hard requirement and disclose material cost or balance information that remains relevant. Mention an unconfirmed higher-priority option only to explain why it was not selected; do not call it ineligible without evidence.
6. If no confirmed candidate meets all requirements, say so plainly, identify the blocking requirement or missing fact, and ask only for the information needed to proceed. Do not use a promotion to override a customer requirement.

## Current product-evidence application

For the supplied account-product evidence, use `references/product_evidence.md` as the factual source. The evidence supports a recommendation of Lime Green when the customer requires all of the following:

- no overdraft fee;
- at least $15 per month in out-of-network ATM-fee rebates; and
- a minimum balance requirement below $10,000.

Lime Green's material disclosure is a $25 monthly maintenance fee unless its $15,000 fee-waiver balance threshold is met. Its $5,000 minimum balance requirement is distinct from that waiver threshold. It also offers dedicated account-manager support.

During the active November 2025 promotional-priority period, Sky Blue is ahead of Lime Green only if it meets every customer requirement and its within-four-years-of-formation condition can be confirmed. If the formation date is unavailable, Sky Blue's eligibility is unknown, not disproven. A confirmed qualifying Lime Green recommendation follows the applicable priority rule.

## Customer-response checklist

A complete response should:

- name only the selected account as the recommendation;
- connect the recommendation to every hard requirement with exact amounts where supported;
- include the relevant maintenance-fee and waiver-threshold disclosure;
- briefly note the useful service perk when relevant to the customer's stated preference;
- explain that the unconfirmed product could be reconsidered after the missing formation information is available, without asking the customer to compare products;
- avoid claims about ATM-owner surcharges, transaction limits, application approval, or other facts not needed and not evidenced for the recommendation.

For the supplied scenario, no account-opening action is requested. If the customer later asks to open an account, follow the separate opening procedure: identity verification and every documented eligibility condition must be completed before using the normal account-opening tool.

## Selector script

`scripts/select_account.py` receives one JSON object on stdin and writes one JSON object on stdout. It uses only supplied runtime facts; it does not create bank actions.

### Input schema

```json
{
  "criteria": {
    "require_zero_overdraft_fee": true,
    "minimum_monthly_atm_rebate": "decimal amount or null",
    "maximum_minimum_balance": "decimal amount or null"
  },
  "promotion": {"active": true, "name": "optional label"},
  "candidates": [
    {
      "name": "product name",
      "eligibility": "confirmed | unknown | ineligible",
      "overdraft_fee": "decimal amount or null",
      "monthly_atm_rebate_cap": "decimal amount or null",
      "minimum_balance_requirement": "decimal amount or null",
      "promotion_priority": "positive integer; lower is higher priority, or null",
      "disclosures": ["evidenced customer-facing disclosure"],
      "perks": ["evidenced relevant perk"]
    }
  ]
}
```

Use JSON numbers or decimal strings for money. Use `null` rather than guessing when a fact is absent. `monthly_atm_rebate_cap` must be the monetary monthly cap applicable to the requested out-of-network usage; do not substitute a count of rebates.

### Output schema

The script returns:

- `status`: `selected`, `no_confirmed_match`, or `needs_data`;
- `selected`: the selected normalized candidate or `null`;
- `qualified_candidates`: all confirmed candidates meeting the hard requirements, in decision order;
- `unconfirmed_candidates`: candidates that might meet requirements but cannot be recommended until eligibility is confirmed;
- `reasons` and `missing_fields`: structured facts for composing a truthful response.

Run it as `python3 scripts/select_account.py < input.json`. Before relying on a `selected` result, confirm that all hard requirements in `criteria` were actually obtained from the customer and that every candidate fact came from applicable product evidence. The script intentionally declines to invent a tie-breaker when no active promotional priority distinguishes otherwise equally ranked confirmed candidates.
