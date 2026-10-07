---
name: business-checking-recommender
description: Provide exactly one evidence-supported business checking recommendation from supplied customer requirements and product documents. Use for read-only guidance about fees, balances, ATM rebates, APY, product eligibility, and applicable promotions; do not use to open, change, or transfer an account.
---

# Business Checking Recommender

Use the supplied conversation, clarification answers, product documents, and read-only time information to provide one direct, supported business checking recommendation.

## Scope and safety

- This is a read-only recommendation workflow. Do not verify identity, inspect customer accounts, request account-opening prerequisites, open an account, or call banking tools merely to make a recommendation.
- Treat the opening request and all clarification answers as one conversation. Requirements remain active until the customer explicitly changes or withdraws them.
- Use only account terms, eligibility conditions, and promotion dates supported by supplied evidence. Do not invent benefits, account eligibility, fees, rates, or rebate amounts.
- The customer asked for one account rather than a comparison. When the active requirements identify a qualifying account, provide the recommendation in that response. Do not defer because an account could later be opened.
- Do not request legal structure, formation documents, identity, ownership, or opening prerequisites for a read-only recommendation unless a documented product-specific eligibility condition makes that fact necessary to choose the account.
- A request to open an account after a recommendation is a separate banking action. Do not treat a general desire to open an account as authorization to perform an opening action.

## 1. Extract active requirements

Separate hard constraints from preferences. Treat wording such as **must**, **need**, **at least**, **cannot**, **non-negotiable**, **zero**, **under**, and **below** as hard constraints.

Apply comparisons exactly:

| Customer wording | Qualification rule |
| --- | --- |
| Maximum overdraft fee | Account overdraft fee is less than or equal to the stated maximum. |
| At least a stated monthly ATM rebate | Documented cap for eligible out-of-network ATM-fee rebates is at least that amount. |
| Minimum balance is “under” or “below” an amount | Documented minimum-balance requirement is strictly less than that amount. |
| Other maximum minimum-balance wording | Documented minimum-balance requirement is less than or equal to that amount. |
| At least a stated APY | Documented APY is at least that percentage. |

A minimum-balance requirement and a monthly-maintenance-fee waiver threshold are distinct. Never use a waiver threshold as the account's minimum-balance requirement.

## 2. Evaluate supported candidates

For each plausible account, extract the evidence-supported values relevant to active hard constraints:

- account name;
- overdraft fee;
- minimum-balance requirement;
- monthly cap for **eligible** out-of-network ATM-fee rebates;
- APY;
- monthly maintenance fee and fee-waiver threshold, when documented; and
- product-specific eligibility conditions and promotion rank, when applicable.

Classify product-specific eligibility from facts actually established in the conversation:

- `eligible`: no documented product-specific condition remains unresolved;
- `unknown`: a required condition is not established or cannot be confirmed;
- `ineligible`: known customer facts conflict with a documented condition.

A candidate with `unknown` eligibility is not a qualifying selection. Do not infer eligibility from favorable terms or promotional priority. General account-opening prerequisites do not restrict a read-only recommendation.

## 3. Select one account

Run `scripts/recommend.py` using the extracted constraints and candidates.

- Set `minimum_balance_exclusive` to `true` for “under” or “below.”
- A qualifying candidate must be `eligible`, have a documented value for every active hard constraint, and satisfy every comparison.
- An active promotion ranks candidates only after they qualify. It cannot override a hard requirement, undocumented terms, or unknown eligibility.
- If the script returns validation errors, correct the evidence extraction before responding.
- If `recommended` is non-null, respond with that one account immediately. Do not ask unrelated questions, claim terms are unavailable, or transfer to a human agent.

### Completion gate

After the customer has supplied enough hard requirements to determine a supported fit:

1. Evaluate the documented candidates with `scripts/recommend.py`.
2. If an eligible candidate qualifies, name exactly one selected account and explicitly state the selected account's documented value for **every** hard requirement.
3. If the selected account has a monthly maintenance fee and waiver threshold material to the customer's stated balance expectations, disclose both as a tradeoff. A maintenance fee is not a hard disqualifier unless the customer made avoiding it a requirement.
4. If a higher-ranked promoted account was excluded because a product-specific eligibility condition is unknown, optionally add one short factual sentence explaining that condition. Do not frame it as a second recommendation.
5. Do not use `transfer_to_human_agents` to obtain catalog terms or a recommendation where supplied evidence supports an answer.

## 4. Render and send the recommendation

When the hard requirements include overdraft fee, minimum balance, ATM rebates, and APY, run `scripts/render_recommendation.py` after selection. Supply the selected account's documented values and, when material, both maintenance-fee fields.

Only use the returned `message` when `errors` is empty. Send that message to the customer as normal natural-language content; a script result by itself is not a customer-facing response.

The recommendation message must explicitly associate all values with the selected account and include:

- `I recommend [account name].`
- its overdraft fee;
- its minimum balance requirement;
- its eligible out-of-network ATM-fee rebate cap per month; and
- its APY.

If no eligible candidate satisfies all hard constraints, state the unmet constraint or unresolved product-specific eligibility fact. Ask only for a missing fact that could establish eligibility, or ask whether the customer wishes to relax a requirement. Do not transfer merely because no selection is currently available.

## Script interfaces

### `scripts/recommend.py`

Reads one JSON object from stdin and emits one JSON object on stdout.

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

It returns `recommended`, `qualifying_candidates`, `blocked_candidates`, and `errors`. `recommended` is null when no fully eligible candidate meets every supplied hard constraint.

### `scripts/render_recommendation.py`

Reads one JSON object from stdin and emits either `{"message":"...","errors":[]}` or a null message with validation errors.

```json
{
  "name": "<selected account name>",
  "overdraft_fee": "<decimal>",
  "minimum_balance": "<decimal>",
  "monthly_atm_rebate": "<decimal>",
  "apy": "<decimal percent>",
  "monthly_maintenance_fee": "<optional decimal; supply with waiver balance>",
  "maintenance_fee_waiver_balance": "<optional decimal; supply with maintenance fee>",
  "higher_priority_note": "<optional source-supported explanation>"
}
```

## If the customer asks to open an account

A recommendation is not authorization to open an account. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a business-checking opening, also verify that the customer is verified; has at least one existing personal checking account with status OPEN; has no more than six business checking accounts; has no accounts with status CLOSED; and has at least $500 in the existing checking account. Confirm the exact desired `account_class` before using the authorized account-opening workflow. If any prerequisite is missing or fails, do not attempt the opening action.
