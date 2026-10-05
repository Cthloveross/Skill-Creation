---
name: evidence-grounded-business-checking-recommender
description: Recommend exactly one business checking account when a customer has stated preferences and the supplied account evidence includes eligibility, fees, benefits, and any time-limited recommendation priority. Use for advice only; use the account-opening procedure only if the customer subsequently asks to open the selected account.
---

# Evidence-Grounded Business Checking Recommender

## Purpose

Turn the current customer's stated requirements and the supplied account documentation into one concise, supportable recommendation. This Skill is designed for situations where the customer does not want a comparison list.

Do not treat vague preferences such as “easy to use” or “most perks” as a reason to invent product attributes. Clarify the concrete priority when needed, then apply only confirmed requirements and documented product facts.

## Required runtime inputs

Extract the following from the current task at runtime:

1. **Customer requirements and confirmed clarifications**: e.g., maximum acceptable overdraft fee, minimum monthly ATM-fee rebate, and company-age confirmation.
2. **Candidate facts** from the supplied documents. Preserve qualifiers such as “eligible,” “up to,” minimums, fees, and eligibility restrictions.
3. **Current date/time**, if a promotion may affect the ordering.
4. **Promotion terms**, including start date, end date, and priority order.

Never assume a candidate satisfies a requirement when its relevant fact is absent or unclear.

## Decision procedure

1. Identify all explicit hard requirements. A customer saying they need no overdraft fee means the documented overdraft fee must be $0. A request for at least a stated ATM rebate amount requires a documented monthly rebate at or above that amount.
2. Confirm product-specific eligibility. For an age-limited account, use a confirmed age or a confirmed upper bound; do not infer age from the type of business.
3. Exclude any account that fails a hard requirement or has insufficient evidence to verify it.
4. If an active promotion specifies an ordering among accounts that all meet the requirements, apply that order. Promotion priority never permits recommending an account that fails a customer requirement. Treat start and end dates as inclusive.
5. If no active promotion resolves the choice, use only documented customer-relevant benefits and explicit customer priorities. Do not manufacture a ranking from missing information.
6. Recommend just the selected account. State the matched requirements and relevant, material caveats. Do not present a list of rejected alternatives unless the customer asks for one.

Use `scripts/select_account.py` to make the filtering and dated-priority decision reproducible. It deliberately rejects incomplete candidate facts rather than guessing.

## Script interface

`scripts/select_account.py` reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD or ISO timestamp",
  "profile": {
    "company_age_years": "number, optional exact age",
    "company_age_at_most": "number, optional confirmed upper bound"
  },
  "requirements": {
    "max_overdraft_fee": "number, optional",
    "min_atm_rebate_monthly": "number, optional"
  },
  "candidates": [
    {
      "id": "stable internal label",
      "name": "customer-facing account name",
      "eligibility": {"max_company_age_years": "number, if age-limited"},
      "fees": {"overdraft_fee": "number, if required"},
      "perks": {"atm_rebate_monthly": "number, if required"},
      "preference_score": "optional documented tie-break score",
      "customer_benefit_notes": ["optional factual notes for the response"],
      "cautions": ["optional factual caveats for the response"]
    }
  ],
  "promotions": [
    {
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "priority": ["candidate id in first-to-last priority order"]
    }
  ]
}
```

Only include a field when it is supported by the current evidence. Monetary values are numeric dollar amounts. If company eligibility is confirmed only as “within N years,” put `N` in `profile.company_age_at_most`; this safely proves eligibility only for a candidate whose maximum age is at least `N`.

Output contains `status`, a selected `recommendation` when one exists, the active promotion priority used (if any), and per-candidate rejection reasons. A `no_qualifying_candidate` result is not permission to select the closest product.

## Customer response method

For a successful selection, write a direct response in this order:

1. Lead with: “I recommend **[account name]**.”
2. Tie the recommendation to each material requirement actually verified from the evidence.
3. Mention only the selected account’s pertinent documented benefits.
4. Give meaningful caveats that could affect the decision. For ATM programs, distinguish the institution’s documented fee/rebate from third-party operator surcharges, and do not promise that a surcharge is covered unless the evidence says so.
5. If appropriate, offer next steps without starting an account-opening action.

Do not claim that an initially charged ATM fee will definitely be rebated beyond the documented monthly cap or eligibility conditions. Do not claim an international fee is waived merely because an ATM-rebate feature exists.

## If the customer asks to open the recommended account

Recommendation does not require identity verification or an account-opening tool call. Opening is a separate request. Before opening a business checking account, confirm all documented prerequisites: verified identity; at least one OPEN personal checking account; no more than six business checking accounts; no CLOSED accounts; and an existing checking-account balance of at least $500. Confirm the desired account class before using the documented opening procedure. If the required opening tool is not available in the runtime, explain that the account cannot be opened through the current session rather than claiming it was opened.

## Validation checklist

Before sending the customer-facing answer, verify that:

- every stated hard requirement is represented in the script input and passes for the selected account;
- any age restriction is affirmatively supported by the clarification;
- a promotion was used only when the supplied current date falls within its stated window;
- dollars, percentages, caps, and time periods match the source exactly;
- no operator surcharge, eligibility, account-opening, or rebate outcome is overstated; and
- the response names one recommendation, not a comparison table.
