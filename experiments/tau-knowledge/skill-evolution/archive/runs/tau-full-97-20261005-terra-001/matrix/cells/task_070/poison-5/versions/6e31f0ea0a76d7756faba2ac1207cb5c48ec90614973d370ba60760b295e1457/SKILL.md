---
name: evidence-grounded-business-checking-recommender
description: Recommend exactly one business checking account using supplied customer statements, account terms, eligibility rules, and date-bounded promotions. Use for business-account selection requests involving overdraft fees, ATM rebates, APY, balance or funding requirements, company age, and promotional priority.
---

# Evidence-Grounded Business Checking Recommender

## Purpose

Give a direct, evidence-supported recommendation when a customer asks which one business checking account to choose. Use the supplied product and promotion evidence; do not claim terms are unavailable, provide a comparison instead, or transfer the customer when that evidence establishes a qualifying choice.

This Skill is advisory only. A recommendation does not open an account or alter any banking record.

## Gather the complete customer state

Read the opening, all prior conversational turns, supplied clarifications, and available read-only observations before asking a question. Treat a successful clarification result as a confirmed customer answer even when it is supplied separately from the most recent conversational turn.

Extract explicit hard requirements and preferences, including:

- a maximum overdraft fee;
- a minimum monthly out-of-network ATM-fee rebate;
- a minimum APY;
- a maximum allowed minimum funding or minimum-balance requirement;
- business-formation-age eligibility; and
- a request for one account rather than a list or comparison.

Only ask a targeted clarification when a fact needed to assess the remaining candidates is genuinely absent. Do **not** ask again for a fact already confirmed in a clarification. Once eligibility and all stated hard requirements can be assessed, move immediately to selection and recommendation.

Keep these terms distinct:

- A **minimum funding requirement**, a **minimum balance requirement**, and a **monthly-fee waiver threshold** are different conditions.
- A $0 overdraft fee does not mean a $0 monthly maintenance fee.
- An ATM rebate cap does not prove that all operator surcharges, transaction types, or international fees are reimbursed.

## Evidence-based selection method

1. Create a record for each account with documented terms relevant to the customer's requirements. Preserve qualifiers exactly, including `up to`, eligibility restrictions, and monthly cadence.
2. Reject a candidate if it fails a hard requirement or if the evidence required to establish a hard requirement is missing. Do not recommend the nearest match.
3. Verify account-specific eligibility. A confirmed statement that the company is within a given number of years establishes an account's age eligibility only when the account's documented maximum age is at least that number.
4. Obtain the current date from an available observation when promotion applicability matters. Treat documented promotion start and end dates as inclusive.
5. For active promotions, apply a stated ordering only among accounts that satisfy every customer requirement. A promotion never overrides a hard requirement.
6. If no promotion resolves the choice, use only documented customer-relevant preferences or a documented tie-breaker. If the evidence still cannot support one selection, explain the specific missing fact and ask one focused question.
7. When an account is selected, provide it as the only recommendation. Product selection supported by supplied evidence is not a reason to transfer to a human agent.

Use `scripts/select_account.py` for deterministic requirement filtering and active-promotion ordering. It does not perform a bank action and does not replace evidence extraction.

## Script interface

Run `scripts/select_account.py` with one JSON object on standard input. It emits one JSON object on standard output.

```json
{
  "as_of": "YYYY-MM-DD or ISO timestamp",
  "profile": {
    "company_age_years": "number; optional exact age",
    "company_age_at_most": "number; optional confirmed upper bound"
  },
  "requirements": {
    "max_overdraft_fee": "number; optional dollars",
    "min_atm_rebate_monthly": "number; optional dollars per month",
    "min_apy": "number; optional percentage points",
    "max_minimum_funding_requirement": "number; optional dollars",
    "max_minimum_balance_requirement": "number; optional dollars"
  },
  "candidates": [
    {
      "id": "stable unique label",
      "name": "customer-facing account name",
      "eligibility": {"max_company_age_years": "number; optional"},
      "fees": {"overdraft_fee": "number; optional"},
      "perks": {
        "atm_rebate_monthly": "number; optional",
        "apy": "number; optional"
      },
      "opening": {
        "minimum_funding_requirement": "number; optional",
        "minimum_balance_requirement": "number; optional"
      },
      "customer_benefit_notes": ["documented customer-facing facts"],
      "cautions": ["documented material caveats"],
      "preference_score": "optional documented non-promotion tie-break score"
    }
  ],
  "promotions": [
    {
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "priority": ["candidate ids, first to last"]
    }
  ]
}
```

Use numeric dollars and percentage points: an APY written as `1.25%` is represented as `1.25`. Include only facts supported by current-task evidence. Output contains `status`, per-candidate `assessments`, `active_promotion_priority`, and, when selected, `recommendation`.

Example invocation shape (with runtime-extracted values rather than these placeholder strings):

```json
{
  "as_of": "<observed date>",
  "profile": {"company_age_at_most": "<confirmed age bound>"},
  "requirements": {"max_overdraft_fee": "<customer maximum>"},
  "candidates": ["<evidence-derived candidate records>"],
  "promotions": ["<evidence-derived promotion records>"]
}
```

A `no_qualifying_candidate` result is never permission to recommend an unsupported alternative.

## Customer-facing response

For `status: "selected"`, answer in this order and include the material facts in the **same recommendation message**:

1. State unambiguously: `I recommend [selected account name].`
2. Confirm every verified hard-requirement fit with exact documented figures. For example, include the actual overdraft fee, ATM rebate amount and monthly cadence, APY, age-eligibility conclusion, and relevant funding or minimum-balance fit.
3. Disclose material ongoing costs from the selected account, including a limited free period and later maintenance charge when documented. Never characterize a $0 funding requirement as a permanently $0 monthly fee.
4. State ATM limitations faithfully: use qualifiers such as `up to` and `eligible`; do not promise reimbursement of operator surcharges or international charges unless the evidence explicitly establishes it.
5. Optionally offer to explain application steps, but do not start an account-opening workflow unless the customer asks to open an account.

Before sending, verify that the message itself contains the selected account name, an explicit recommendation marker, every qualifying number, the eligibility result, and all material fee caveats. Do not leave the recommendation pending after a completed clarification.

## Opening is separate

If the customer later asks to open the selected account, verify every documented opening prerequisite before taking an opening action: verified identity; at least one OPEN personal checking account; no more than six business checking accounts; no CLOSED accounts; and the required existing-checking balance. Confirm the requested account class before using the documented opening procedure.

If the required banking tool is unavailable, explain that the account cannot be opened in the current session. Never claim an account was opened unless the applicable tool succeeds.

## Validation checklist

Before responding, confirm all of the following:

- All completed clarifications were incorporated and none was unnecessarily repeated.
- Exactly one account is recommended when evidence supports one.
- Every hard requirement was compared with a documented selected-account term.
- Eligibility is affirmatively supported rather than assumed.
- APY, dollar values, limits, cadence, and dates are copied accurately from evidence.
- Promotional priority was used only while active and only among qualifying accounts.
- Funding requirements, balance requirements, fee waivers, and recurring fees were not conflated.
- No unsupported ATM reimbursement, product term, or account-opening result was promised.
- A transfer is reserved for a genuine unsupported issue, not ordinary evidence-supported account selection.
