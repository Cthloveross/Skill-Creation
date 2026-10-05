---
name: business-checking-recommender
description: Recommend one business checking account from supplied product facts when a customer states requirements such as zero overdraft fees, a maximum acceptable minimum balance, ATM-fee rebates, APY, and eligibility. Use for an informational recommendation only; do not use to open or modify an account.
---

# Business Checking Recommender

Use this Skill to turn a customer's stated needs and the currently supported product facts into one defensible recommendation. It is designed to avoid treating unknown eligibility as a match and to apply a time-limited promotional preference only after all hard customer requirements have been met.

## Scope and assumptions

- This is an informational product comparison, not a banking action. Do not verify identity or invoke account-opening tools merely to make a recommendation.
- Extract only requirements the customer actually states. Distinguish a hard requirement (for example, "$0 overdraft fees is non-negotiable") from a preference.
- Obtain all product facts, eligibility conditions, promotion status, and current date from the current task's supplied knowledge and observations. Do not infer missing terms or reuse facts from another customer or product catalog.
- A product whose required eligibility is unknown is **not** a qualifying recommendation. It may be described briefly as conditional, with the exact missing fact needed to assess it.
- Clearly disclose material tradeoffs of the selected product that are relevant to the customer's circumstances, such as a maintenance fee and its waiver threshold. Do not imply a fee is waived unless the customer has established that they satisfy its waiver condition.

## Method

1. Summarize the customer's hard constraints and preferences in neutral terms.
2. Gather a normalized record for every potentially relevant account. Include only facts supported by the supplied sources:
   - `overdraft_fee`
   - `minimum_balance`
   - `monthly_atm_rebate`
   - `apy`
   - eligibility status and the reason if not established
   - a promotion priority only when the promotion is active on the observed date.
3. Run `scripts/recommend.py` with the records and constraints.
4. If the script returns a recommendation, provide exactly that one account as the recommendation. State the facts that satisfy each hard constraint and material fee terms. Do not make the customer compare a list.
5. If a higher-priority promotional product is blocked only by unknown eligibility, say it is not being recommended until that eligibility is confirmed; do not present it as equally qualifying.
6. If no product qualifies, explain which stated constraints prevent a supported recommendation and ask only for information that could resolve a conditional eligibility issue or indicate the requirement the customer might relax.

For a response, lead with a direct recommendation, then give a short bullet list mapping it to the hard requirements, followed by any relevant fee caveat. Cite product names and values from the supplied sources accurately.

## Script interface

`scripts/recommend.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "requirements": {
    "max_overdraft_fee": "0.00",
    "max_minimum_balance": "<decimal, optional>",
    "min_monthly_atm_rebate": "<decimal, optional>",
    "min_apy": "<decimal percent, optional>"
  },
  "promotion_active": true,
  "candidates": [
    {
      "name": "<account name>",
      "overdraft_fee": "<decimal>",
      "minimum_balance": "<decimal>",
      "monthly_atm_rebate": "<decimal>",
      "apy": "<decimal percent>",
      "eligibility": {"status": "eligible|ineligible|unknown", "reason": "<required if not eligible>"},
      "promotion_rank": 1
    }
  ]
}
```

`max_overdraft_fee` is optional; include it when the customer has an overdraft-fee limit. `promotion_rank` is a positive integer where a lower number is preferred, and is considered only when `promotion_active` is true. Fields used by a stated requirement must be supplied for every candidate; otherwise that candidate is marked blocked for missing data.

Output schema:

```json
{
  "recommended": {"name": "...", "reasons": ["..."]} | null,
  "qualifying_candidates": ["..."],
  "blocked_candidates": [{"name": "...", "reasons": ["..."]}],
  "errors": ["..."]
}
```

A nonempty `errors` array means the input cannot support a reliable decision. A `null` recommendation with no errors means no fully eligible candidate met every stated constraint.

### Runnable example

```sh
printf '%s\n' '{"requirements":{"max_overdraft_fee":"0","max_minimum_balance":"5000","min_monthly_atm_rebate":"10","min_apy":"1"},"promotion_active":false,"candidates":[{"name":"Account A","overdraft_fee":"0","minimum_balance":"5000","monthly_atm_rebate":"12","apy":"1.1","eligibility":{"status":"eligible"}},{"name":"Account B","overdraft_fee":"0","minimum_balance":"3000","monthly_atm_rebate":"8","apy":"1.4","eligibility":{"status":"eligible"}}]}' | python3 scripts/recommend.py
```

Validate that `errors` is empty, `recommended` is non-null, and every listed reason corresponds to a stated constraint before using the result in a customer response. The example is illustrative only; always provide current task facts at runtime.

## If the customer asks to open the recommended account

Do not open an account based on this recommendation alone. First confirm the exact product/class and obtain the required account-opening information. Preserve and follow this control for any banking action:

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a business-checking opening, also verify the customer is verified; has at least one OPEN personal checking account; has no more than six business checking accounts; has no CLOSED accounts; and has at least $500 in the existing checking account. Confirm the desired `account_class` before using the authorized account-opening workflow/tool. If any prerequisite is unavailable or fails, explain that opening cannot proceed and do not attempt the action.
