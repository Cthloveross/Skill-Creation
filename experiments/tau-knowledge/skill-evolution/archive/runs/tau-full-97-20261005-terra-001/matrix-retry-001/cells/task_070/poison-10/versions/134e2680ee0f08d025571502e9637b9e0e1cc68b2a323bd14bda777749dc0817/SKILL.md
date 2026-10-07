---
name: business-checking-recommender
description: Recommend exactly one evidence-supported business checking account after collecting a customer's hard requirements for overdraft fees, balance requirements, ATM rebates, APY, and product-specific eligibility. Use for read-only product guidance, not account opening or account changes.
---

# Business Checking Recommender

Convert the supplied customer statements, read-only observations, promotion notices, and product documents into one direct, customer-facing business-checking recommendation.

## Scope and safety

- This Skill is for informational product recommendations only. Do not verify identity, inspect customer accounts, open an account, or call account-opening tools merely to recommend a product.
- Read all supplied customer messages, clarifications, product documents, promotion notices, and relevant date/time observations before deciding.
- Never invent a fee, rate, balance requirement, rebate, eligibility outcome, waiver, or product term.
- The customer requested one account. Once a supported fit exists, answer directly; do not give a comparison list, say that terms are unavailable, defer for catalog access, or transfer instead of answering.
- A transfer is not a substitute for a recommendation. Handle a later, independent request for a human only under the normal transfer policy.

## 1. Capture all active requirements

Extract every customer requirement from the opening and every clarification. Classify each as a hard constraint or a preference. Keep earlier hard constraints active when later clarifications add requirements.

Treat language such as **must**, **need at least**, **cannot**, **non-negotiable**, **zero**, and **under** as hard constraints. Interpret directions precisely:

| Customer wording | Qualification rule |
| --- | --- |
| maximum overdraft fee | product fee is less than or equal to the maximum |
| at least a monthly ATM-fee rebate amount | documented cap for eligible out-of-network ATM-fee rebates is greater than or equal to the minimum |
| balance requirement **under** an amount | documented minimum-balance requirement is strictly less than that amount |
| maximum balance requirement | requirement is less than or equal to the stated maximum unless the customer says “under,” “below,” or otherwise makes it exclusive |
| at least an APY | product APY is greater than or equal to the minimum |

A minimum-balance requirement is distinct from a maintenance-fee waiver threshold. Preserve that distinction during selection and in the response.

## 2. Extract candidate facts from supplied evidence

For every plausible account, record only source-supported facts:

- account name;
- overdraft fee;
- minimum-balance requirement;
- monthly cap for **eligible** out-of-network ATM-fee rebates;
- APY;
- product-specific eligibility conditions; and
- promotion rank if an applicable promotion is active at the observed time.

Determine product eligibility from the information actually supplied:

- `eligible`: no unresolved product-specific condition prevents recommendation on the available facts.
- `unknown`: the product requires a customer fact that is not confirmed.
- `ineligible`: supplied customer facts contradict a required product condition.

Do not infer eligibility from favorable product terms or promotional status. An account with an unconfirmed product-specific condition is `unknown` and cannot qualify.

General prerequisites for the later act of opening an account do not prevent an informational recommendation. Address them only if the customer asks to open an account.

## 3. Select one supported account

Use `scripts/recommend.py` with all extracted candidates and hard constraints.

- Set `minimum_balance_exclusive` to `true` when the customer says the minimum balance must be “under” or “below” a ceiling.
- The script rejects candidates with missing evidence needed to assess a hard constraint, unmet constraints, or eligibility other than `eligible`.
- A candidate qualifies only when its eligibility is established and it meets every hard constraint.
- If multiple candidates qualify, use an active promotion rank only to order those qualifying candidates. A promotion never overrides unmet requirements or unknown eligibility.

Before answering, confirm that `errors` is empty and `recommended` is non-null. When the supplied catalog supports a result, do not claim it is unavailable and do not ask another question merely to revisit already-known requirements.

## 4. Deliver the recommendation

When a candidate is selected, give the answer in the same response as the completed selection:

1. Begin: **“I recommend [account name].”**
2. Explicitly associate each hard requirement with the selected account's documented value.
3. If overdraft fee, minimum balance, ATM rebates, and APY are all hard constraints, use `scripts/render_recommendation.py`; do not remove any of its four factual bullets.
4. If a higher-priority promoted candidate was excluded because eligibility is unconfirmed, briefly say that its required eligibility condition could not be confirmed and that promotion ordering applies only among accounts meeting all stated requirements.
5. State a material source-supported tradeoff when relevant, such as a separate monthly maintenance fee and its waiver threshold. Do not represent a fee as waived unless the customer is documented to meet the waiver condition.

Do not turn the response into a comparison list. Do not transfer merely to obtain terms or make a recommendation when evidence supports one.

If no account qualifies, identify the blocking hard constraint or unresolved product eligibility and ask only for the specific missing fact that could establish eligibility or the requirement the customer may wish to relax.

## Script interfaces

### `scripts/recommend.py`

Reads one JSON object on stdin and emits one JSON object on stdout.

Input:

```json
{
  "requirements": {
    "max_overdraft_fee": "<non-negative decimal, optional>",
    "minimum_balance_upper_bound": "<non-negative decimal, optional>",
    "minimum_balance_exclusive": "<boolean; default false>",
    "min_monthly_atm_rebate": "<non-negative decimal, optional>",
    "min_apy": "<non-negative decimal percent, optional>"
  },
  "promotion_active": true,
  "candidates": [
    {
      "name": "<account name>",
      "overdraft_fee": "<decimal when required>",
      "minimum_balance": "<decimal when required>",
      "monthly_atm_rebate": "<decimal when required>",
      "apy": "<decimal percent when required>",
      "eligibility": {
        "status": "eligible|ineligible|unknown",
        "reason": "<required for ineligible or unknown>"
      },
      "promotion_rank": 1
    }
  ]
}
```

`minimum_balance_exclusive` applies only when `minimum_balance_upper_bound` is supplied. Output contains `recommended`, `qualifying_candidates`, `blocked_candidates`, and `errors`. `recommended` is null when no fully eligible candidate meets every supplied constraint.

### `scripts/render_recommendation.py`

Use after selecting a candidate when the customer has hard constraints for overdrafts, minimum balance, ATM rebates, and APY. It reads:

```json
{
  "name": "<selected account name>",
  "overdraft_fee": "<decimal>",
  "minimum_balance": "<decimal>",
  "monthly_atm_rebate": "<decimal>",
  "apy": "<decimal percent>",
  "higher_priority_note": "<optional supported explanation>",
  "tradeoff": "<optional supported tradeoff>"
}
```

It emits `{"message":"...", "errors":[]}`. Verify `errors` is empty before using `message`. The executor may add concise source-supported context but must not remove or contradict the rendered facts.

## If the customer asks to open the recommended account

A recommendation is not authorization to open an account. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a business-checking opening, also verify that the customer is verified; has at least one existing personal checking account with status OPEN; has no more than six business checking accounts; has no accounts with status CLOSED; and has at least $500 in the existing checking account. Confirm the exact desired `account_class` before using the authorized account-opening workflow. If a prerequisite is missing or fails, do not attempt the opening action.
