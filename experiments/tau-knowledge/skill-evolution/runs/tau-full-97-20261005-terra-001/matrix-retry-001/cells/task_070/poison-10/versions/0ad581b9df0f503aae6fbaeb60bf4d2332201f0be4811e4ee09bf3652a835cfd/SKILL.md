---
name: business-checking-recommender
description: Provide exactly one evidence-supported business checking recommendation after a customer states their account requirements. Use for read-only product guidance involving fees, balance requirements, ATM rebates, APY, eligibility, and active promotions; do not use it to open or modify an account.
---

# Business Checking Recommender

Turn the supplied customer conversation, product documents, promotion notices, and read-only time observations into one direct, customer-facing recommendation.

## Scope and safety

- This Skill provides informational recommendations only. Do not verify identity, inspect customer accounts, request account-opening prerequisites, open an account, or call banking tools merely to recommend a product.
- Read every customer statement and clarification. Earlier requirements remain active unless the customer explicitly changes or withdraws them.
- Use only facts supported by the supplied product evidence. Never invent product terms, eligibility, fees, rates, waivers, or promotion status.
- The customer wants one account, not a comparison. Once sufficient requirements and product facts are available, provide the recommendation in that same turn. Do not claim the catalog is unavailable, ask unrelated questions, or transfer instead of answering.
- A later request to open an account is a distinct banking action and requires the relevant opening workflow and all of its prerequisites.

## 1. Capture requirements

Extract each customer statement into either a hard constraint or a preference. Treat words such as **must**, **need**, **at least**, **cannot**, **non-negotiable**, **zero**, **under**, and **below** as hard constraints.

Apply comparison language exactly:

| Customer requirement | Product qualification rule |
| --- | --- |
| Maximum overdraft fee | Overdraft fee is less than or equal to the maximum. |
| At least a stated ATM rebate | Monthly cap for eligible out-of-network ATM-fee rebates is at least that amount. |
| Minimum balance is “under” or “below” an amount | Documented minimum-balance requirement is strictly less than that amount. |
| Maximum balance requirement without exclusive wording | Minimum-balance requirement is less than or equal to that amount. |
| At least a stated APY | APY is at least that percentage. |

A minimum-balance requirement and a maintenance-fee waiver threshold are separate terms. Do not treat a waiver threshold as the minimum balance requirement, and do not imply that meeting a minimum balance waives a maintenance fee unless the evidence says so.

## 2. Build evidence-supported candidates

For each plausible account, collect only documented values for the relevant constraints:

- account name;
- overdraft fee;
- minimum-balance requirement;
- monthly cap for **eligible** out-of-network ATM-fee rebates;
- APY;
- monthly maintenance fee and its waiver threshold when documented; and
- product-specific eligibility conditions and promotion rank, if applicable.

Set product eligibility based on the customer facts actually available:

- `eligible`: no unresolved product-specific condition blocks selection;
- `unknown`: a required eligibility fact is absent or cannot be confirmed; or
- `ineligible`: supplied customer facts conflict with an eligibility condition.

Do not assume eligibility from favorable pricing or a promotion. A candidate with `unknown` eligibility is not a qualifying recommendation. General account-opening requirements do not affect a read-only recommendation.

## 3. Select the one account

Call `scripts/recommend.py` with the extracted hard constraints and candidates.

- Set `minimum_balance_exclusive` to `true` for “under” or “below.”
- A qualifying candidate must be `eligible`, have documented values for every hard constraint, and meet every comparison.
- If multiple candidates qualify, active promotional rank orders only those qualifying candidates. It never overrides a hard constraint or unresolved eligibility.
- If the script returns a nonempty `errors` list, correct the extraction/input problem before making a recommendation.
- If `recommended` is non-null, give that answer immediately. Do not ask for legal structure, identity, account ownership, formation documents, or other details unrelated to the selected candidate's documented eligibility.

### Mandatory completion gate

Before sending a response after the customer has supplied all active hard requirements, check the following:

1. If at least one fully eligible candidate meets every requirement, the response **must** name exactly one selected account and state its documented values for every hard requirement.
2. If a higher-ranked promoted product was not selected because its eligibility is unknown, say briefly that the relevant eligibility condition cannot currently be confirmed and that promotions apply only among qualifying accounts.
3. When the selected account has a documented maintenance fee and fee-waiver threshold that is material to the customer's stated balance expectations, disclose both terms. Do not silently substitute the waiver threshold for the minimum balance.
4. Never transfer merely to obtain product terms or a recommendation when the supplied evidence already supports one.

## 4. Render the customer-facing answer

When overdraft fee, minimum balance, ATM rebates, and APY are hard requirements, call `scripts/render_recommendation.py` after selection. Supply the selected documented values. Also supply `monthly_maintenance_fee` and `maintenance_fee_waiver_balance` together when those documented terms are material.

The rendered response begins with `I recommend [account name].` and expressly ties each documented term to the chosen account. Use its complete `message` only when `errors` is empty. You may add one concise, source-supported eligibility note about an excluded higher-priority account, but do not turn the response into a comparison list.

If no candidate qualifies, say what hard constraint is unmet or which product-specific eligibility fact remains unresolved. Ask only for a missing fact that could establish eligibility, or identify the requirement the customer could choose to relax. Do not transfer merely because no selection is immediately available.

## Script interfaces

### `scripts/recommend.py`

Reads one JSON object from stdin and writes one JSON object to stdout.

```json
{
  "requirements": {
    "max_overdraft_fee": "<non-negative decimal, optional>",
    "minimum_balance_upper_bound": "<non-negative decimal, optional>",
    "minimum_balance_exclusive": true,
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
        "reason": "<required unless eligible>"
      },
      "promotion_rank": 1
    }
  ]
}
```

It returns `recommended`, `qualifying_candidates`, `blocked_candidates`, and `errors`. `recommended` is null if no fully eligible candidate satisfies every supplied constraint.

### `scripts/render_recommendation.py`

Reads one JSON object from stdin and writes `{"message": "...", "errors": []}` or a null message with validation errors.

```json
{
  "name": "<selected account name>",
  "overdraft_fee": "<decimal>",
  "minimum_balance": "<decimal>",
  "monthly_atm_rebate": "<decimal>",
  "apy": "<decimal percent>",
  "monthly_maintenance_fee": "<optional decimal; must accompany waiver balance>",
  "maintenance_fee_waiver_balance": "<optional decimal; must accompany maintenance fee>",
  "higher_priority_note": "<optional source-supported explanation>"
}
```

## If the customer asks to open an account

A recommendation is not authorization to open an account. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a business-checking opening, also verify that the customer is verified; has at least one existing personal checking account with status OPEN; has no more than six business checking accounts; has no accounts with status CLOSED; and has at least $500 in the existing checking account. Confirm the exact desired `account_class` before using the authorized account-opening workflow. If any prerequisite is missing or fails, do not attempt the opening action.
