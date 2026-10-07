---
name: banking-account-needs-recommendation
description: Recommend checking and savings accounts from supplied product evidence after eliciting needs. Use for advisory conversations involving travel, fees, balances, savings yield, eco features, and premium-account suitability. Produces a concise, evidence-grounded customer response without performing account actions.
---

# Banking account needs recommendation

Use this Skill to turn a customer conversation and the supplied product documentation into a clear recommendation. It is an advisory Skill: do not open, modify, or link accounts, and do not imply that an account has been opened.

## Inputs

At runtime, collect:

- the opening request and all clarification answers;
- the customer's stated existing products only if explicitly stated;
- the supplied product evidence/catalogue; and
- any current-time observation if the response needs a date (it normally does not).

`scripts/recommend_accounts.py` accepts JSON on stdin and emits a structured recommendation. Its input schema is:

```json
{
  "profile": {
    "international_travel": true,
    "frequent_foreign_atm_use": true,
    "foreign_currency_purchases": true,
    "desired_currency_holding": true,
    "reliable_daily_checking_balance": 3750,
    "interested_in_eco_savings": true,
    "savings_priority": null,
    "expected_savings_balance": null
  },
  "catalog": { "checking": [], "savings": [] }
}
```

The `catalog` entries use the fields documented in that script. Supply `null` for facts not established. Do not guess missing customer facts.

## Method

1. **Separate the decisions.** A customer can have a strong checking fit while still needing one final savings preference. Do not let an incomplete savings profile prevent a useful checking recommendation.
2. **Extract hard constraints first.** Examples include a maximum sustainable daily balance, foreign-transaction-fee aversion, need to hold currencies, frequent foreign ATM use, and an existing account the customer wants to keep separate.
3. **Eliminate unsuitable accounts before comparing benefits.** In particular, do not recommend a premium checking account if its opening or ongoing-balance requirement exceeds the customer's stated capacity. State the relevant threshold and consequence plainly.
4. **Evaluate total travel cost.** Distinguish all of the following rather than treating them as one fee:
   - the bank's foreign transaction fee;
   - the bank's foreign ATM withdrawal fee;
   - third-party ATM operator surcharges;
   - any monthly reimbursement cap; and
   - any conversion markup.
   A reimbursement cap does not mean unlimited reimbursement, and a zero bank fee does not erase a third-party surcharge.
5. **Check fee-waiver feasibility.** If the recommended account has a monthly fee that can be waived, recommend it as a fit only when the customer said they can reliably meet—not merely occasionally reach—the daily-balance threshold. Mention the fee if the balance falls below it.
6. **Assess savings independently.** Compare APY, opening deposit, ongoing balance, monthly fee, access/withdrawal constraints, and eco features. If the user has not named a savings priority or expected balance, give a provisional evidence-based option and ask one focused follow-up instead of fabricating a final yield/fee fit.
7. **Validate linked-product claims.** Only claim a linked-checking APY boost when the exact checking/savings pairing is listed as eligible. A customer's multiple checking boosts do not stack; the highest applicable checking boost is the only checking boost used. Credit-card bonuses must likewise be described only if supported by the evidence.
8. **Be decisive but transparent.** Lead with a single best checking recommendation when the evidence supports one. Give a short reasoned alternative only when it materially changes the tradeoff. Avoid an exhausting product list.

## Customer-facing response template

Use plain language and cover the points relevant to the conversation:

1. Acknowledge the travel, balance, and/or eco priorities.
2. State the recommended checking account and why it satisfies each stated travel constraint.
3. State important limitations: fee-waiver balance, monthly rebate cap, operator-fee distinction, conversion markup, and account-opening requirement where applicable.
4. Address the premium/exclusive option directly if asked, including why it does or does not fit the stated funds.
5. Recommend a savings account if the stated information is sufficient; otherwise label it provisional and ask exactly one high-value savings question (priority and approximate balance can be combined).
6. Mention any eligibility caveat for an APY boost rather than promising one.
7. Invite the customer to confirm before any next step. Do not claim to enroll them or recommend unsupported products.

## Required validation

Before sending the response, verify:

- Every numerical claim is present in the supplied evidence/catalogue.
- The chosen checking account satisfies all stated hard constraints, or every exception is disclosed.
- Bank fee, third-party ATM surcharge, reimbursement cap, and conversion pricing are not conflated.
- A premium account is not presented as suitable when its balance/opening requirement conflicts with the customer profile.
- No linked APY boost is claimed without the exact pairing.
- Missing savings goals are called out as missing rather than assumed.
- No personal-data lookup, identity verification, account change, or account-opening tool is used for a recommendation-only request.

## Runnable helper example

Create a JSON input using the runtime's actual transcript-derived facts and evidence catalogue, then run:

```text
python3 scripts/recommend_accounts.py < request.json
```

The script emits JSON with `checking`, `savings`, `warnings`, `missing_information`, and `validation_errors`. Interpret an empty `validation_errors` array as a structural check only; it does not replace checking every claim against the supplied evidence.
