---
name: business-checking-recommender
description: Provide exactly one evidence-supported business checking recommendation from supplied customer requirements and product documents. Use for read-only guidance about fees, balances, ATM rebates, APY, eligibility, and time-limited promotions; do not use to open, change, or transfer an account.
---

# Business Checking Recommender

Use the supplied conversation, clarifications, product documents, and read-only time information to give the customer one direct, supported account recommendation.

## Scope and safety

- This is a read-only product recommendation workflow. Do not verify identity, inspect customer accounts, request opening prerequisites, open an account, or call banking tools merely to recommend an account.
- Treat all customer statements and clarification answers as part of one conversation. A requirement remains active unless the customer explicitly changes or withdraws it.
- Use only terms supported by supplied product evidence. Do not invent account features, eligibility, rates, fees, rebates, or promotion dates.
- The customer requested one account, not a comparison. Once the active requirements are sufficient to identify a qualifying account, answer immediately in the same response. Do not defer, claim terms are unavailable, ask unrelated questions, or transfer instead of making a supported recommendation.
- Do not require legal structure, formation documents, identity, ownership, or account-opening information for a recommendation unless a documented product-specific eligibility condition makes that fact necessary to select the product.
- If the customer later asks to open the selected account, that is a separate banking action governed by the account-opening workflow and its prerequisites.

## 1. Extract active requirements

Separate requirements into hard constraints and softer preferences. Treat terms such as **must**, **need**, **at least**, **cannot**, **non-negotiable**, **zero**, **under**, and **below** as hard constraints.

Apply comparisons exactly:

| Customer wording | Qualification rule |
| --- | --- |
| Maximum overdraft fee | Account overdraft fee is less than or equal to the maximum. |
| At least a stated ATM rebate | Cap for eligible out-of-network ATM-fee rebates is at least that amount. |
| Minimum balance is “under” or “below” an amount | Documented minimum-balance requirement is strictly less than that amount. |
| Maximum balance without exclusive wording | Minimum-balance requirement is less than or equal to that amount. |
| At least a stated APY | APY is at least that percentage. |

A minimum-balance requirement and a monthly-maintenance-fee waiver threshold are different facts. Never substitute one for the other.

## 2. Assess candidates from the supplied evidence

For each plausible account, extract only documented values relevant to the active hard constraints:

- account name;
- overdraft fee;
- minimum-balance requirement;
- monthly cap for **eligible** out-of-network ATM-fee rebates;
- APY;
- documented monthly maintenance fee and fee-waiver threshold; and
- product-specific eligibility conditions and active-promotion rank, if any.

Classify each candidate's eligibility from facts actually available in the conversation:

- `eligible`: no documented product-specific condition remains unresolved;
- `unknown`: a required product-specific eligibility fact is absent or cannot be confirmed;
- `ineligible`: known customer facts conflict with a documented condition.

Do not assume eligibility from favorable terms or a promotion. A candidate with unknown eligibility is not a qualifying selection. General opening prerequisites do not limit a read-only recommendation.

## 3. Select exactly one account

Call `scripts/recommend.py` with the extracted hard constraints and candidates.

- Set `minimum_balance_exclusive` to `true` for “under” or “below.”
- A qualifying candidate must be `eligible`, have documented values for every hard constraint, and satisfy every comparison.
- A promotion orders candidates only after they qualify. It cannot override a hard requirement, a missing product term, or unresolved eligibility.
- If the script reports errors, correct the extraction before responding.
- If `recommended` is non-null, provide that recommendation immediately. Do not seek unrelated information first.

### Completion gate

Before responding after the customer has supplied all active hard requirements:

1. Build candidate data from the supplied evidence and run `scripts/recommend.py`.
2. If a fully eligible candidate qualifies, name exactly one selected account and give its documented value for **every** hard requirement in the response.
3. If the selected account has a documented maintenance fee and waiver threshold material to the customer's balance expectations, disclose both as a tradeoff.
4. If a higher-ranked promoted candidate was excluded because eligibility is unknown, optionally give one short factual sentence explaining that the specific eligibility condition is unconfirmed and promotions apply only among qualifying accounts. Do not present it as a second recommendation.
5. Do not make a human-transfer call merely to obtain terms or a recommendation when the supplied evidence supports an answer.

## 4. Render the response

When overdraft fee, minimum balance, ATM rebates, and APY are hard requirements, call `scripts/render_recommendation.py` after selection. Pass the selected, documented values and, when material, both maintenance-fee fields.

Use its complete `message` only if `errors` is empty. It produces the required customer-facing form:

- `I recommend [account name].`
- the account's overdraft fee;
- its minimum balance requirement;
- its eligible out-of-network ATM-fee rebate cap per month; and
- its APY.

The values must be explicitly associated with the selected account, not merely repeated as the customer's wishes. If relevant, add the concise excluded-promoted-account note after the rendered message.

If no candidate qualifies, state the unmet hard constraint or the product-specific eligibility fact that is unresolved. Ask only for a missing fact that could establish product eligibility, or identify a requirement the customer could choose to relax. Do not transfer merely because no selection is currently possible.

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

It returns `recommended`, `qualifying_candidates`, `blocked_candidates`, and `errors`. `recommended` is null when no fully eligible candidate meets every supplied constraint.

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
