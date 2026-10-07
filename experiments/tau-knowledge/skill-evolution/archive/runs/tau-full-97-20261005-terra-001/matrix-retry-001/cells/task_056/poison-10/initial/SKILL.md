---
name: business-checking-account-recommendation
description: Recommend a business checking account from supplied account terms and customer needs. Use for informational comparisons, fee-waiver analysis, eligibility-sensitive recommendations, and promotion-aware ranking; do not use it to open, modify, or close an account.
---

# Business Checking Account Recommendation

Use this Skill to produce a transparent recommendation from the account facts supplied with the current task. It is designed for advice only. Do not treat a recommendation as an account-opening request or make a banking change while using this workflow.

## Method

1. Extract only explicit customer requirements and preferences. Separate:
   - **Hard requirements**, such as zero overdraft fees, a required payment type, or a maximum balance that can reliably be kept in checking.
   - **Preferences**, such as avoiding a monthly fee, cashback, cards for employees, or higher mobile-deposit limits.
   - **Unknowns**, such as a formation date needed for an eligibility rule. Do not assume an unknown fact is satisfied.
2. Build one structured record per candidate from account-specific documentation. Keep values associated with the correct account; do not infer an account's terms from another account's documentation.
3. Check hard requirements first. A candidate with a known conflict is excluded. A candidate requiring an unknown eligibility or feature fact is conditional, not confirmed as qualifying.
4. For a monthly-fee waiver, compare the waiver threshold with the amount the customer can **reliably** maintain. If the customer supplied a range, use the lower end for reliable-waiver analysis. Explain that a threshold met only occasionally does not establish a reliable waiver.
5. Apply a time-bounded promotion only after confirming the candidate meets all hard requirements. Rank active promotional candidates in their documented order; never recommend a promotional account that fails a stated need or has unverified eligibility.
6. Rank remaining confirmed candidates by whether the monthly fee is reliably avoidable, then by known monthly cost and lower reliable balance threshold. Use documented features only as tie-breakers when they are customer preferences.
7. State one primary recommendation if there is a confirmed fit. Also state important conditions and alternatives, including why an otherwise notable account was not selected. If no confirmed fit exists, ask only for the missing facts that could change the outcome.

Use `scripts/recommend_accounts.py` for consistent screening and ranking. The executor remains responsible for converting its structured result into a concise customer-facing answer with account-specific citations from the supplied materials.

## Script interface

The script reads one JSON object from stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "as_of": "YYYY-MM-DD or timestamp",
  "requirements": {
    "zero_overdraft_required": true,
    "reliably_maintainable_balance": 0,
    "balance_range": {"minimum": 0, "maximum": 0},
    "avoid_monthly_fee": true,
    "must_waive_monthly_fee": false,
    "required_features": ["feature_key"]
  },
  "candidates": [
    {
      "name": "Account name",
      "overdraft_fee": 0,
      "monthly_fee": 0,
      "waiver_balance": 0,
      "eligibility": {"criterion": true},
      "features": {"feature_key": true},
      "sources": ["source identifier"]
    }
  ],
  "promotions": [
    {
      "name": "Account name",
      "starts_on": "YYYY-MM-DD",
      "ends_on": "YYYY-MM-DD",
      "priority": 1
    }
  ],
  "exclude_names": ["Account already held or otherwise excluded"]
}
```

`eligibility` may instead be `true`, `false`, or `null`. For criterion maps, `true` means confirmed, `false` means ineligible, and `null` means unknown. `features` accepts the same true/false/null convention. Omit unknown monetary values rather than inventing them. `balance_range.minimum` is used only when `reliably_maintainable_balance` is absent.

The response has `qualified`, `conditional`, `excluded`, `recommendation`, and `questions` fields. `recommendation` is the highest-ranked confirmed candidate or `null`. Monetary amounts are emitted as decimal strings to avoid float rounding ambiguity.

Example invocation through the packaged runtime:

```json
{
  "relative_path": "scripts/recommend_accounts.py",
  "input_json": {
    "as_of": "YYYY-MM-DD",
    "requirements": {
      "zero_overdraft_required": true,
      "reliably_maintainable_balance": 0,
      "avoid_monthly_fee": true
    },
    "candidates": [],
    "promotions": []
  }
}
```

An empty candidate list is valid and returns targeted missing-data questions. Before relying on a nonempty result, validate that every candidate has a name and that any cited fee, waiver, eligibility, and feature fields are supported by the current task materials.

## Customer-facing response requirements

- Lead with the selected account and the hard requirements it meets.
- Explain the fee result precisely: the stated monthly fee, applicable waiver threshold, and whether the customer's reliable balance supports that waiver.
- Identify eligibility prerequisites as conditions rather than asserting them as true when the customer has not provided them.
- Mention promotions only if the supplied date is within the inclusive promotion dates and the promoted account is confirmed to meet every hard requirement.
- Do not claim that an account has “more features” unless named features are documented and relevant to the customer.
- Do not promise approval, fee reversal, availability, or an action that has not occurred.

## If the customer wants to open an account

Recommendation is informational. Before proceeding to an opening request, confirm the customer identity, authority, desired account class, and the documented opening eligibility conditions: verified customer; at least one existing OPEN personal checking account; no more than six business checking accounts; no CLOSED accounts; and at least $500 in the existing checking account. Only then use the documented account-opening workflow and its approved banking tool if available in the runtime.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

If those prerequisites cannot be verified, do not perform the banking action. Continue with general information or explain the missing prerequisites instead.
