---
name: business-checking-account-recommendation
description: Make a direct, evidence-based business checking recommendation from supplied account documents and a customer's stated needs. Use for informational comparisons, fee-waiver analysis, promotion-aware ranking, and eligibility-sensitive alternatives; do not use to open, modify, or close an account.
---

# Business Checking Account Recommendation

Use this Skill when a customer asks which business checking account is right for them. This is an informational workflow, not an account-opening or account-change workflow.

## Non-deferral rule

When the supplied conversation and account materials establish at least one **confirmed fit**, provide one direct recommendation. Do not claim that terms are unavailable when they are present in the supplied materials, and do not transfer merely because another account has an unresolved eligibility condition.

Prior clarifying answers in the current conversation are already customer inputs. Do not restart discovery or ask the customer to repeat them when they are sufficient to evaluate a documented account.

## Decision method

1. Collect all stated facts from the opening request and clarifications. Separate them into:
   - **Hard requirements**, such as no overdraft fees, a maximum monthly cost, or a mandatory capability.
   - **Preferences**, such as reliably avoiding a maintenance fee, more operational features, ATM rebates, card rewards, or cards for employees.
   - **Unknown eligibility facts**, such as a formation date required by a particular product.
2. Build one record per candidate from the supplied documents only. Attach each account's fee, waiver threshold and measurement basis, overdraft policy, eligibility terms, and features to that same account. Never merge features across products.
3. For a balance range, use the lower end as the reliable balance unless the customer explicitly says otherwise. A waiver is reliably available only if that amount meets the documented waiver threshold.
4. Exclude accounts with a known hard-requirement conflict. Mark an account **conditional**, not confirmed, if a necessary eligibility fact or required feature is unknown. Never assume an unknown fact is satisfied.
5. Apply a currently active promotion only among accounts that are confirmed fits. A promotion cannot override a hard conflict or unresolved eligibility.
6. Rank confirmed fits by active applicable promotional priority, coverage of stated preferences, reliable fee avoidance, lower known cost/waiver threshold, and other documented advantages. An account the customer already describes as too basic should not be selected merely because it is inexpensive when another confirmed account better meets the stated upgrade preferences.
7. Recommend the highest-ranked confirmed fit. If there is no confirmed fit, ask only for the missing fact(s) that could change the decision; explain known conflicts rather than guessing.

Use `scripts/recommend_accounts.py` to screen and rank structured records when comparing more than one account. It has no embedded catalog: populate it solely from the current task's materials.

## Required response content

For a confirmed recommendation, write a customer-facing answer that:

1. Opens with: the named account is the **best confirmed fit** (or equally clear direct wording).
2. Explicitly addresses every hard requirement, especially a zero-overdraft-fee requirement.
3. States the monthly maintenance fee, exact waiver threshold, and threshold basis where documented. Relate the threshold to the customer's reliable balance.
4. If cash flow can fall below the threshold, say plainly that the maintenance fee can apply during those periods and recommend a balance alert. Do not imply a waiver is guaranteed.
5. Names the actual documented practical features that motivated the recommendation, with their limits or rates. For example, state an ATM-rebate cap, debit-purchase cashback rate and eligibility qualifier, and number of business debit cards when those are relevant and documented.
6. If discussing a promoted account with unresolved eligibility, label it as conditional and state the exact verification needed. Do not call it eligible, qualifying, or the best fit.
7. Does not promise account approval, fee reversals, or any banking action.

When structured terms have been prepared, use `scripts/compose_recommendation.py` to render the core response. Review its result against the source records before sending it; omit a feature rather than filling a missing value from memory.

## Ranking script interface

`scripts/recommend_accounts.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

- `as_of`: required ISO date or timestamp for promotion evaluation.
- `requirements`: object with optional boolean `zero_overdraft_required`, numeric `reliably_maintainable_balance`, numeric `maximum_monthly_fee`, boolean `must_waive_monthly_fee`, string arrays `required_features` and `preferred_features`.
- `candidates`: array of records with required `name`; optional `overdraft_fee`, `monthly_fee`, `waiver_balance`, `eligibility`, `features`, and `sources`.
- `promotions`: optional array of `{name, starts_on, ends_on, priority}` records.

`eligibility` is `true`, `false`, `null`, or an object with true/false/null values. `features` is an object mapping feature keys to true/false/null. Numeric amounts must be nonnegative. The script emits `recommendation`, `qualified`, `conditional`, `excluded`, and `questions`; a null recommendation means no confirmed fit was supplied.

A runnable structural validation call is:

```json
{"as_of":"2025-01-01","requirements":{},"candidates":[]}
```

Before relying on a nonempty result, verify that candidate names are unique, every supplied term is supported by current materials, and every required preference was represented as a feature key or other applicable requirement.

## Response-composition script interface

`scripts/compose_recommendation.py` reads one JSON object from stdin and writes `{"status":"ok","message":"..."}` on stdout. It requires:

- `recommendation`: a confirmed account record with `name`, `overdraft_fee`, `monthly_fee`, and `waiver_balance` when those terms are known.
- `customer`: optional `reliable_balance` and boolean `cash_flow_variable`.
- `features`: optional object containing documented `atm_rebate_monthly`, `cashback_rate`, `cashback_qualifier`, `business_debit_cards`, and/or `additional` strings.
- `conditional_alternatives`: optional array of `{name, condition}` records.

It rejects missing account names, nonnumeric monetary fields, and alternatives without an explicit condition. Its output is a draft based only on provided values; the executor must ensure those values came from the supplied evidence.

## Opening is separate

If the customer later asks to open an account, first verify identity, authority, desired account class, and every documented opening eligibility requirement. Keep the recommendation separate from the opening process and use only approved banking tools after the required checks.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
