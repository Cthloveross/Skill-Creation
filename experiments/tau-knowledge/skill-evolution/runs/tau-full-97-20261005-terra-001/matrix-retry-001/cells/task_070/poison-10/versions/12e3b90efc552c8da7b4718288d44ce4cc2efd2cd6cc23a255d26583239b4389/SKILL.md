---
name: business-checking-recommender
description: Recommend exactly one supported business checking account from supplied product facts after a customer states requirements such as overdraft fees, minimum balance, ATM-fee rebates, APY, and eligibility. Use for informational product recommendations, not to open or modify an account.
---

# Business Checking Recommender

Use this Skill to turn a customer's stated needs and supplied product evidence into one clear, defensible account recommendation. Apply promotional ordering only after confirming that an account satisfies every hard requirement and has established eligibility.

## Scope and safety

- This is an informational recommendation, not a banking action. Do not verify identity, access customer accounts, or invoke account-opening tools merely to compare products.
- Read the current task's supplied customer messages, clarifications, product documents, promotion documents, and time observation. Do not claim that a catalog or terms are unavailable when supplied documents support an answer.
- Never invent a product term, eligibility result, fee waiver, or account feature. A required but unconfirmed eligibility condition makes that candidate non-qualifying for the present recommendation.
- The customer asked for one account, not a comparison list. Once sufficient facts are available, give the recommendation directly rather than asking another question or escalating.
- Do not transfer to a human merely because product terms or eligibility were considered. Transfer only if the customer later independently requests a human after receiving the supported answer, or if an actual unsupported issue requires it.

## Interpret customer needs

1. Extract each expressed requirement and label it as either:
   - **Hard constraint**: a numeric ceiling/floor or non-negotiable condition (for example, zero overdraft fee, minimum monthly ATM rebate, maximum acceptable minimum balance, minimum APY, or required eligibility).
   - **Preference**: a desired feature that does not disqualify an otherwise suitable account unless the customer makes it mandatory.
2. Treat phrases such as “non-negotiable,” “must,” “need at least,” “cannot,” and “under” as hard constraints.
3. Preserve the customer’s comparison direction accurately. For example, an ATM rebate and APY are minimums, while an acceptable minimum-balance requirement and overdraft fee are maximums.
4. If a clarification supplies a new hard constraint, incorporate it before deciding. Do not continue asking about already-resolved needs once the available evidence supports one fully eligible fit.

## Evidence and qualification procedure

For every potentially relevant account, assemble only supported facts:

- account name;
- overdraft fee;
- minimum balance requirement (do not substitute a fee-waiver threshold unless it is also the stated minimum requirement);
- monthly eligible out-of-network ATM-fee rebate cap;
- APY;
- eligibility status: `eligible`, `ineligible`, or `unknown`, including the source-supported reason for a non-eligible status;
- promotion rank, only if a supplied promotion is active at the observed date.

Then run `scripts/recommend.py` with the structured facts and the customer’s hard constraints.

A candidate qualifies only when all of the following are true:

1. Its eligibility is established as `eligible`.
2. Every field needed for a hard constraint is supplied and valid.
3. It meets every hard constraint.

An `unknown` eligibility status is not a pass. If a promotional account has unknown eligibility, do not recommend it ahead of a fully eligible qualifying account. Mention the unknown condition briefly only when it helps explain why the customer is receiving the selected account instead. Promotion ordering applies only among qualifying candidates.

## Required customer response

When the script returns a non-null recommendation and no errors:

1. Lead with: **“I recommend [account name].”**
2. Map every hard requirement to its exact supported selected-account value. State the feature and value together; do not merely say that the account “meets your needs.” For example, cover the overdraft fee, minimum balance, ATM rebate cap, and APY whenever those are the customer’s constraints.
3. State any material tradeoff supported by the documents that is relevant to the customer’s situation, such as a maintenance fee and its waiver condition. Do not imply that a fee is waived without evidence that the customer meets the waiver condition.
4. If a higher-priority promotional candidate was not selected due to unconfirmed eligibility, give one concise explanation of the eligibility fact that remains unconfirmed and that promotional priority applies only to accounts meeting all stated requirements.
5. Do not present several accounts as co-recommendations, ask for a comparison choice, say the catalog is unavailable, or transfer the customer in place of providing the answer.

Use customer-facing bullets when several hard requirements must be shown. Ensure the final wording contains the selected account name and the concrete numeric values for each stated numeric requirement.

If there is no qualifying candidate and no script error, explain which constraints prevent a supported choice. Ask only for information that could establish eligibility or identify a requirement the customer is willing to relax. If the script reports errors, correct the evidence extraction before making a recommendation.

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
      "eligibility": {
        "status": "eligible|ineligible|unknown",
        "reason": "<required when status is not eligible>"
      },
      "promotion_rank": 1
    }
  ]
}
```

Include a candidate field whenever the customer has a corresponding hard requirement. `promotion_rank` is a positive integer with lower values preferred and is considered only when `promotion_active` is `true`.

Output schema:

```json
{
  "recommended": {
    "name": "<account name>",
    "reasons": ["<matched constraint>"],
    "matched_values": {"overdraft_fee": "<decimal>"}
  },
  "qualifying_candidates": ["<account name>"],
  "blocked_candidates": [{"name": "<account name>", "reasons": ["<reason>"]}],
  "errors": []
}
```

`recommended` is `null` when no fully eligible candidate meets all hard constraints. A nonempty `errors` array means the supplied structured evidence cannot support a reliable decision.

### Runnable example

```sh
printf '%s\n' '{"requirements":{"max_overdraft_fee":"0","max_minimum_balance":"5000","min_monthly_atm_rebate":"10","min_apy":"1"},"promotion_active":false,"candidates":[{"name":"Account A","overdraft_fee":"0","minimum_balance":"5000","monthly_atm_rebate":"12","apy":"1.1","eligibility":{"status":"eligible"}},{"name":"Account B","overdraft_fee":"0","minimum_balance":"3000","monthly_atm_rebate":"8","apy":"1.4","eligibility":{"status":"eligible"}}]}' | python3 scripts/recommend.py
```

Before relying on the result, validate that `errors` is empty, `recommended` is non-null, every customer hard constraint has a corresponding `matched_values` entry, and those values match the supplied source documents.

## If the customer asks to open the recommended account

Do not open an account based on a recommendation alone. First confirm the exact product/class and obtain all required account-opening information. Preserve and follow this control for any banking action:

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a business-checking opening, also verify the customer is verified; has at least one OPEN personal checking account; has no more than six business checking accounts; has no CLOSED accounts; and has at least $500 in the existing checking account. Confirm the desired `account_class` before using the authorized account-opening workflow/tool. If any prerequisite is unavailable or fails, explain that opening cannot proceed and do not attempt the action.
