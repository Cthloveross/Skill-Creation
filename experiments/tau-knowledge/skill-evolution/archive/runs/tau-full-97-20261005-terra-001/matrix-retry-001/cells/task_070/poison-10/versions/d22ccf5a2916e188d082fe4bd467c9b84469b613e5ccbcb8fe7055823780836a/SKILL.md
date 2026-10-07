---
name: business-checking-recommender
description: Provide evidence-supported read-only business-checking guidance from supplied customer requirements and product documents. Use to select one qualifying account when possible or clearly explain documented conflicts when no account can be confirmed to meet every hard requirement; do not use to open, change, or transfer an account.
---

# Business Checking Recommender

Use the supplied conversation, clarification answers, product documents, and read-only time information to give direct, accurate business-checking guidance.

## Scope and safety

- This is a read-only recommendation workflow. Do not verify identity, inspect customer accounts, request account-opening prerequisites, open an account, or call banking tools merely to make a recommendation.
- Treat the opening request and all customer clarification answers as one conversation. A customer requirement remains active until the customer explicitly changes or withdraws it.
- Extract requirements from what the customer says, not from options suggested in an assistant question. A customer can make a constraint hard through terms such as **must**, **need**, **at least**, **cannot**, **non-negotiable**, **zero**, **under**, **below**, or an equivalent clear statement.
- Use only terms, eligibility conditions, and promotion dates supported by supplied evidence. Do not invent account benefits, eligibility, fees, rates, or rebate amounts.
- The customer requested one answer, not a broad comparison. When an account satisfies every active hard requirement, recommend exactly one account. When no account can be confirmed to do so, say that plainly and explain the supported blocker rather than pretending the terms are unavailable.
- A request to open an account after receiving guidance is a separate banking action. Do not treat a general desire to open an account as authorization to perform an opening action.

## 1. Extract active requirements

Separate hard constraints from preferences. Capture the numerical limit and comparison direction exactly.

| Customer wording | Qualification rule |
| --- | --- |
| Maximum overdraft fee | Account overdraft fee is less than or equal to the stated maximum. |
| At least a stated monthly ATM rebate | Documented cap for eligible out-of-network ATM-fee rebates is at least that amount. |
| Minimum balance is “under” or “below” an amount | Documented minimum-balance requirement is strictly less than that amount. |
| Other maximum minimum-balance wording | Documented minimum-balance requirement is less than or equal to that amount. |
| At least a stated APY | Documented APY is at least that percentage. |
| No monthly maintenance fee | Ongoing documented monthly maintenance fee is $0. A temporary introductory free period does not satisfy this requirement if a later ongoing fee applies. |

A minimum-balance requirement, a monthly maintenance fee, and a fee-waiver threshold are separate terms. Never substitute a waiver threshold for the minimum-balance requirement or represent a fee as absent merely because it can be waived at a balance the customer cannot maintain.

## 2. Evaluate supported candidates

For each plausible account, extract only evidence-supported values relevant to the active hard constraints:

- account name;
- overdraft fee;
- minimum-balance requirement;
- monthly cap for **eligible** out-of-network ATM-fee rebates;
- APY;
- ongoing monthly maintenance fee and fee-waiver threshold, when documented; and
- product-specific eligibility conditions and promotion rank, when applicable.

Classify product-specific eligibility from facts established in the conversation:

- `eligible`: no documented product-specific condition remains unresolved;
- `unknown`: a required condition is unestablished or cannot be confirmed;
- `ineligible`: known customer facts conflict with a documented condition.

A candidate with unknown eligibility is not a qualifying selection. Do not infer eligibility from favorable terms or promotional priority. General account-opening prerequisites do not restrict a read-only recommendation.

## 3. Select or explain

Run `scripts/recommend.py` with the extracted constraints and candidates.

- Set `minimum_balance_exclusive` to `true` for “under” or “below.”
- Set `max_monthly_maintenance_fee` to `0` when the customer requires no monthly maintenance fee.
- A qualifying candidate must be `eligible`, have a documented value for every active hard constraint, and satisfy every comparison.
- A promotion ranks candidates only after they qualify. It cannot override a hard requirement, undocumented terms, or unresolved eligibility.
- If the script returns validation errors, correct the evidence extraction before responding.

### If a candidate qualifies

When `recommended` is non-null:

1. Name exactly one selected account and explicitly state the selected account's documented value for every hard requirement.
2. If the selected account has a monthly maintenance fee and waiver threshold material to the customer's stated balance expectations, disclose both as a tradeoff. A maintenance fee is not a disqualifier unless the customer made avoiding it a hard requirement.
3. A higher-ranked promotional account with unknown eligibility may be mentioned only as a short factual exclusion, never as a second recommendation.
4. Do not ask unrelated questions, claim terms are unavailable, or transfer to a human agent.

For the common overdraft/minimum-balance/ATM-rebate/APY case, use `scripts/render_recommendation.py` after selection. Send its `message` only if `errors` is empty.

### If no candidate qualifies

Do not recommend an account as though it satisfies all hard requirements. Instead:

1. State directly that you **cannot confirm any documented account meets every hard requirement**, naming the relevant requirement (for example, “no monthly maintenance fee”).
2. Explain the concrete, documented blocker. Do not say product terms are unavailable when the supplied catalog establishes the conflict.
3. If useful, identify one closest supported option only as a tradeoff, not as an all-requirements recommendation. State both its matching terms and the disqualifying term.
4. Mention unresolved product-specific eligibility only accurately. An unconfirmed eligibility condition cannot be overcome by promotional priority.
5. Ask whether the customer wants the closest fit despite the identified tradeoff or wants to relax one specific requirement. Do not transfer merely because no current all-fit selection exists.

When the no-fit explanation concerns Lime Green's ongoing maintenance fee, use `scripts/render_no_fit.py`. It produces a customer-facing explanation that distinguishes its otherwise matching terms from the fee conflict.

## Documented conflict pattern

If the customer has a hard requirement of no monthly maintenance fee and cannot maintain the stated waiver balance, do not describe Lime Green as satisfying every requirement. The documented Lime Green terms are:

- $0 overdraft fee;
- $5,000 minimum balance requirement;
- 1.5% APY;
- up to $25 per month in eligible out-of-network ATM-fee rebates; and
- a $25 monthly maintenance fee, waived only at a $15,000 balance.

Thus it can be a closest-fit tradeoff for the first four requirements, but not a confirmed all-requirements fit where no monthly maintenance fee is hard. Sky Blue likewise cannot be selected while its within-four-years-of-formation condition is unresolved; its six-month free period does not establish an ongoing no-monthly-fee fit.

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
    "min_apy": "<non-negative decimal percent, optional>",
    "max_monthly_maintenance_fee": "<non-negative decimal, optional>"
  },
  "promotion_active": true,
  "candidates": [
    {
      "name": "<account name>",
      "overdraft_fee": "<decimal when required>",
      "minimum_balance": "<decimal when required>",
      "monthly_atm_rebate": "<decimal when required>",
      "apy": "<decimal percent when required>",
      "monthly_maintenance_fee": "<decimal when required>",
      "eligibility": {
        "status": "eligible|ineligible|unknown",
        "reason": "<required unless eligible>"
      },
      "promotion_rank": 1
    }
  ]
}
```

It returns `recommended`, `qualifying_candidates`, `blocked_candidates`, `closest_candidates`, and `errors`. `recommended` is null when no fully eligible candidate meets every supplied hard constraint. `closest_candidates` are only a diagnostic aid; a returned closest candidate is not a qualifying recommendation.

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

### `scripts/render_no_fit.py`

Reads one JSON object from stdin and emits either `{"message":"...","errors":[]}` or a null message with validation errors.

```json
{
  "name": "<closest account name>",
  "overdraft_fee": "<decimal>",
  "minimum_balance": "<decimal>",
  "monthly_atm_rebate": "<decimal>",
  "apy": "<decimal percent>",
  "monthly_maintenance_fee": "<positive decimal>",
  "maintenance_fee_waiver_balance": "<decimal>",
  "unresolved_eligibility_note": "<optional source-supported explanation>"
}
```

## If the customer asks to open an account

A recommendation is not authorization to open an account. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a business-checking opening, also verify that the customer is verified; has at least one existing personal checking account with status OPEN; has no more than six business checking accounts; has no accounts with status CLOSED; and has at least $500 in the existing checking account. Confirm the exact desired `account_class` before using the authorized account-opening workflow. If any prerequisite is missing or fails, do not attempt the opening action.
